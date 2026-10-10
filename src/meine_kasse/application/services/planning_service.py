"""Kostenstellenplanung: Haushaltsansatz und Monatswerte (siehe Architekturvorgabe 2.7, 2.8).

- Der Basisansatz ist bei aktiver Planung fix und ändert sich dann nur per Ansatzumbuchung.
- Die Verteilung auf Monate läuft hier, ohne Buchung, solange die Summe im Jahresansatz bleibt.
- Abgeschlossene Monate sind gesperrt. Jede Änderung wird protokolliert.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace

from meine_kasse.application.ports import Today, UnitOfWorkFactory, local_today
from meine_kasse.application.services.booking_control_service import load_or_create_control
from meine_kasse.domain.entities import AuditEntry, CostCenter, CostCenterPlan, MonthlyPlan
from meine_kasse.domain.enums import CostCenterKind, PlanMode
from meine_kasse.domain.errors import NotFoundError, PeriodError, ValidationError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.planning_rules import (
    MONTHS,
    check_distribution,
    validate_month_amounts,
    validate_plan_amounts,
)
from meine_kasse.domain.value_objects.money import format_euro

_FIXED_BASE_MESSAGE = (
    "Der Haushaltsansatz ist bei aktiver Planung fix. "
    "Änderungen sind nur durch Ansatzumbuchung möglich."
)


@dataclass(frozen=True, slots=True)
class MonthPlanInput:
    month: int
    plan_cents: int
    reserve_plan_cents: int = 0
    plan_mode: PlanMode = PlanMode.MONTHLY


@dataclass(frozen=True, slots=True)
class PlanMonthView:
    """Ein Monat der Planung mit Ist-Werten (Soll und Haben getrennt) und Status."""

    month: int
    plan_cents: int
    reserve_plan_cents: int
    plan_mode: PlanMode
    debit_cents: int
    credit_cents: int
    is_closed: bool

    @property
    def movement_cents(self) -> int:
        return self.debit_cents - self.credit_cents

    @property
    def deviation_cents(self) -> int:
        """Plan - Ist-Bewegung. Positiv heißt: noch Planbetrag übrig."""
        return self.plan_cents - self.movement_cents


@dataclass(frozen=True, slots=True)
class PlanView:
    cost_center_id: str
    year: int
    planning_enabled: bool
    year_closed: bool
    base_budget_cents: int
    budget_transfer_cents: int
    reserve_carry_in_cents: int
    reserve_carry_out_cents: int
    months: tuple[PlanMonthView, ...]

    @property
    def effective_budget_cents(self) -> int:
        return self.base_budget_cents + self.budget_transfer_cents

    @property
    def distributed_cents(self) -> int:
        return sum(month.plan_cents for month in self.months)

    @property
    def undistributed_cents(self) -> int:
        return self.effective_budget_cents - self.distributed_cents

    @property
    def movement_cents(self) -> int:
        return sum(month.movement_cents for month in self.months)

    @property
    def remaining_cents(self) -> int:
        return self.effective_budget_cents - self.movement_cents

    @property
    def base_editable(self) -> bool:
        return not self.planning_enabled and not self.year_closed


class PlanningService:
    def __init__(self, uow_factory: UnitOfWorkFactory, today: Today = local_today) -> None:
        self._uow_factory = uow_factory
        self._today = today

    def list_planned_cost_centers(self) -> Sequence[CostCenter]:
        """Aktive Kostenstellen mit Plan (Art `STANDARD`)."""
        with self._uow_factory() as uow:
            return [
                cost_center
                for cost_center in uow.cost_centers.list_all()
                if cost_center.is_active and cost_center.kind is CostCenterKind.STANDARD
            ]

    def get_plan_view(self, cost_center_id: str, year: int) -> PlanView:
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            _get_planned_cost_center(uow, cost_center_id)
            plan = uow.plans.get_plan(cost_center_id, year)
            monthly = {item.month: item for item in uow.plans.monthly_plans(cost_center_id, year)}
            actuals = {a.month: a for a in uow.plans.actuals_for_year(cost_center_id, year)}
            closed_months = uow.closures.closed_months()
            year_closed = year in uow.closures.closed_years()
            months = []
            for month in MONTHS:
                planned = monthly.get(month)
                actual = actuals.get(month)
                months.append(
                    PlanMonthView(
                        month=month,
                        plan_cents=planned.plan_cents if planned else 0,
                        reserve_plan_cents=planned.reserve_plan_cents if planned else 0,
                        plan_mode=planned.plan_mode if planned else PlanMode.MONTHLY,
                        debit_cents=actual.debit_cents if actual else 0,
                        credit_cents=actual.credit_cents if actual else 0,
                        is_closed=year_closed or (year, month) in closed_months,
                    )
                )
            return PlanView(
                cost_center_id=cost_center_id,
                year=year,
                planning_enabled=control.planning_enabled,
                year_closed=year_closed,
                base_budget_cents=plan.base_budget_cents if plan else 0,
                budget_transfer_cents=plan.budget_transfer_cents if plan else 0,
                reserve_carry_in_cents=plan.reserve_carry_in_cents if plan else 0,
                reserve_carry_out_cents=plan.reserve_carry_out_cents if plan else 0,
                months=tuple(months),
            )

    def save_plan(
        self,
        cost_center_id: str,
        year: int,
        *,
        base_budget_cents: int,
        reserve_carry_in_cents: int = 0,
        reserve_carry_out_cents: int = 0,
        months: Sequence[MonthPlanInput],
        actor_id: str,
    ) -> None:
        validate_plan_amounts(
            base_cents=base_budget_cents,
            carry_in_cents=reserve_carry_in_cents,
            carry_out_cents=reserve_carry_out_cents,
        )
        seen: set[int] = set()
        for item in months:
            validate_month_amounts(item.month, item.plan_cents, item.reserve_plan_cents)
            if item.month in seen:
                raise ValidationError(f"Der Monat {item.month:02d} ist mehrfach angegeben.")
            seen.add(item.month)

        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            _get_planned_cost_center(uow, cost_center_id)
            if year in uow.closures.closed_years():
                raise PeriodError(
                    f"Das Jahr {year} ist abgeschlossen und kann nicht geplant werden."
                )

            existing_plan = uow.plans.get_plan(cost_center_id, year)
            plan = existing_plan or CostCenterPlan(new_id(), cost_center_id, year)
            if control.planning_enabled and base_budget_cents != plan.base_budget_cents:
                raise ValidationError(_FIXED_BASE_MESSAGE)

            existing_months = {
                item.month: item for item in uow.plans.monthly_plans(cost_center_id, year)
            }
            closed_months = uow.closures.closed_months()
            for item in months:
                if (year, item.month) in closed_months and _differs(
                    existing_months.get(item.month), item
                ):
                    raise PeriodError(
                        f"Der Monat {item.month:02d}/{year} ist abgeschlossen. "
                        "Die Planung kann dort nicht mehr geändert werden."
                    )

            new_plan = replace(
                plan,
                base_budget_cents=base_budget_cents,
                reserve_carry_in_cents=reserve_carry_in_cents,
                reserve_carry_out_cents=reserve_carry_out_cents,
            )
            new_months = dict(existing_months)
            for item in months:
                current = existing_months.get(item.month)
                new_months[item.month] = MonthlyPlan(
                    id=current.id if current else new_id(),
                    cost_center_plan_id=new_plan.id,
                    month=item.month,
                    plan_cents=item.plan_cents,
                    reserve_plan_cents=item.reserve_plan_cents,
                    plan_mode=item.plan_mode,
                )
            check_distribution(
                new_plan.effective_budget_cents,
                sum(month.plan_cents for month in new_months.values()),
            )

            before = _snapshot(existing_plan, existing_months)
            after = _snapshot(new_plan, new_months)
            changed = {key for key in after if before.get(key) != after[key]}
            if not changed and existing_plan is not None:
                return

            uow.plans.save_plan(new_plan)
            for item in months:
                current = existing_months.get(item.month)
                if current is None and not _has_content(item):
                    continue
                uow.plans.save_monthly_plan(new_months[item.month])
            uow.audit.add(
                AuditEntry(
                    name="PLAN_UPDATED",
                    entity="cost_center_plans",
                    entity_id=new_plan.id,
                    user_id=actor_id,
                    old_value=json.dumps(
                        {key: before.get(key, "–") for key in sorted(changed)}, ensure_ascii=False
                    ),
                    new_value=json.dumps(
                        {key: after[key] for key in sorted(changed)}, ensure_ascii=False
                    ),
                )
            )
            uow.commit()


def _get_planned_cost_center(uow: UnitOfWork, cost_center_id: str) -> CostCenter:
    cost_center = uow.cost_centers.get(cost_center_id)
    if cost_center is None:
        raise NotFoundError("Die Kostenstelle wurde nicht gefunden.")
    if cost_center.kind is not CostCenterKind.STANDARD:
        raise ValidationError("Für Kostenstellen ohne Plan gibt es keine Planung.")
    return cost_center


def _has_content(item: MonthPlanInput) -> bool:
    return (
        bool(item.plan_cents or item.reserve_plan_cents) or item.plan_mode is not PlanMode.MONTHLY
    )


def _differs(current: MonthlyPlan | None, item: MonthPlanInput) -> bool:
    if current is None:
        return _has_content(item)
    return (current.plan_cents, current.reserve_plan_cents, current.plan_mode) != (
        item.plan_cents,
        item.reserve_plan_cents,
        item.plan_mode,
    )


def _snapshot(plan: CostCenterPlan | None, months: dict[int, MonthlyPlan]) -> dict[str, str]:
    values = {
        "base_budget": format_euro(plan.base_budget_cents if plan else 0),
        "reserve_carry_in": format_euro(plan.reserve_carry_in_cents if plan else 0),
        "reserve_carry_out": format_euro(plan.reserve_carry_out_cents if plan else 0),
    }
    for month in MONTHS:
        item = months.get(month)
        values[f"m{month:02d}_plan"] = format_euro(item.plan_cents if item else 0)
        values[f"m{month:02d}_reserve"] = format_euro(item.reserve_plan_cents if item else 0)
        values[f"m{month:02d}_mode"] = (item.plan_mode if item else PlanMode.MONTHLY).value
    return values
