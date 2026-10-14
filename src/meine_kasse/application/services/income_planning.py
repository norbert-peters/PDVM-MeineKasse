"""Einnahmenplanung (Architekturvorgabe 2.15).

Für Kostenstellen der Art `INCOME` ist `plan_cents` je Monat die erwartete Einnahme. Es gibt keinen
Jahresansatz, keine Rückstellung und keine Ansatzsperre. Der Plan darf nicht unter den bereits
weitergegebenen Betrag sinken, soweit dieser nur durch den Plan gedeckt ist (Modus `PLAN`).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from meine_kasse.application.services.income_position import income_position
from meine_kasse.domain.entities import AuditEntry, CostCenter, CostCenterPlan, MonthlyPlan
from meine_kasse.domain.enums import CostCenterKind, IncomeMode, PlanMode
from meine_kasse.domain.errors import NotFoundError, PeriodError, ValidationError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.income_rules import IncomePosition, check_coverage
from meine_kasse.domain.services.planning_rules import MONTHS, validate_month_amounts
from meine_kasse.domain.value_objects.money import format_euro


@dataclass(frozen=True, slots=True)
class IncomeMonthInput:
    month: int
    plan_cents: int


@dataclass(frozen=True, slots=True)
class IncomeMonthView:
    """Ein Monat: erwartete Einnahme, gebuchte Einnahme (Haben − Soll) und Status."""

    month: int
    plan_cents: int
    debit_cents: int
    credit_cents: int
    is_closed: bool

    @property
    def realized_cents(self) -> int:
        return self.credit_cents - self.debit_cents

    @property
    def deviation_cents(self) -> int:
        """Ist − Plan. Positiv heißt: mehr eingenommen als erwartet."""
        return self.realized_cents - self.plan_cents


@dataclass(frozen=True, slots=True)
class IncomeView:
    cost_center_id: str
    year: int
    mode: IncomeMode
    year_closed: bool
    passed_on_cents: int
    months: tuple[IncomeMonthView, ...]

    @property
    def position(self) -> IncomePosition:
        return IncomePosition(
            self.mode, self.planned_cents, self.realized_cents, self.passed_on_cents
        )

    @property
    def planned_cents(self) -> int:
        return sum(month.plan_cents for month in self.months)

    @property
    def realized_cents(self) -> int:
        return sum(month.realized_cents for month in self.months)

    @property
    def available_cents(self) -> int:
        return self.position.available_cents

    @property
    def free_cents(self) -> int:
        return self.position.free_cents

    @property
    def open_expected_cents(self) -> int:
        """Noch erwartete Einnahme des Jahres: je Monat Plan abzüglich Ist, nie negativ."""
        return sum(max(0, month.plan_cents - month.realized_cents) for month in self.months)

    def with_plan(self, plan_cents: dict[int, int]) -> Self:
        """Die Ansicht mit geänderten Planwerten (für die Live-Anzeige im Dialog)."""
        months = tuple(
            IncomeMonthView(
                item.month,
                plan_cents.get(item.month, item.plan_cents),
                item.debit_cents,
                item.credit_cents,
                item.is_closed,
            )
            for item in self.months
        )
        return type(self)(
            self.cost_center_id,
            self.year,
            self.mode,
            self.year_closed,
            self.passed_on_cents,
            months,
        )


def get_income_cost_center(uow: UnitOfWork, cost_center_id: str) -> CostCenter:
    cost_center = uow.cost_centers.get(cost_center_id)
    if cost_center is None:
        raise NotFoundError("Die Kostenstelle wurde nicht gefunden.")
    if cost_center.kind is not CostCenterKind.INCOME:
        raise ValidationError("Das ist keine Einnahmen-Kostenstelle.")
    return cost_center


def build_income_view(uow: UnitOfWork, cost_center: CostCenter, year: int) -> IncomeView:
    plans = {item.month: item for item in uow.plans.monthly_plans(cost_center.id, year)}
    actuals = {item.month: item for item in uow.plans.actuals_for_year(cost_center.id, year)}
    closed_months = uow.closures.closed_months()
    year_closed = year in uow.closures.closed_years()
    months = []
    for month in MONTHS:
        planned, actual = plans.get(month), actuals.get(month)
        months.append(
            IncomeMonthView(
                month=month,
                plan_cents=planned.plan_cents if planned else 0,
                debit_cents=actual.debit_cents if actual else 0,
                credit_cents=actual.credit_cents if actual else 0,
                is_closed=year_closed or (year, month) in closed_months,
            )
        )
    return IncomeView(
        cost_center_id=cost_center.id,
        year=year,
        mode=cost_center.income_mode or IncomeMode.PLAN,
        year_closed=year_closed,
        passed_on_cents=income_position(uow, cost_center, year).passed_on_cents,
        months=tuple(months),
    )


def save_income_plan(
    uow: UnitOfWork,
    cost_center: CostCenter,
    year: int,
    months: Sequence[IncomeMonthInput],
    actor_id: str,
) -> bool:
    """Speichert die erwarteten Einnahmen. Gibt zurück, ob sich etwas geändert hat."""
    seen: set[int] = set()
    for item in months:
        validate_month_amounts(item.month, item.plan_cents, None)
        if item.month in seen:
            raise ValidationError(f"Der Monat {item.month:02d} ist mehrfach angegeben.")
        seen.add(item.month)
    if year in uow.closures.closed_years():
        raise PeriodError(f"Das Jahr {year} ist abgeschlossen und kann nicht geplant werden.")

    existing_plan = uow.plans.get_plan(cost_center.id, year)
    plan = existing_plan or CostCenterPlan(new_id(), cost_center.id, year)
    existing = {item.month: item for item in uow.plans.monthly_plans(cost_center.id, year)}
    closed_months = uow.closures.closed_months()
    new_values = {month: existing[month].plan_cents if month in existing else 0 for month in MONTHS}
    for item in months:
        current = new_values[item.month]
        if (year, item.month) in closed_months and item.plan_cents != current:
            raise PeriodError(
                f"Der Monat {item.month:02d}/{year} ist abgeschlossen. "
                "Die Planung kann dort nicht mehr geändert werden."
            )
        new_values[item.month] = item.plan_cents

    before = {m: existing[m].plan_cents if m in existing else 0 for m in MONTHS}
    changed = {m for m in MONTHS if new_values[m] != before[m]}
    if not changed and existing_plan is not None:
        return False

    current_position = income_position(uow, cost_center, year)
    check_coverage(
        IncomePosition(
            current_position.mode,
            sum(new_values.values()),
            current_position.realized_cents,
            current_position.passed_on_cents,
        ),
        reason="Der Plan kann nicht in dieser Höhe verringert werden.",
    )

    uow.plans.save_plan(plan)
    for month in sorted(changed):
        current_month = existing.get(month)
        uow.plans.save_monthly_plan(
            MonthlyPlan(
                id=current_month.id if current_month else new_id(),
                cost_center_plan_id=plan.id,
                month=month,
                plan_cents=new_values[month],
                reserve_plan_cents=0,
                plan_mode=PlanMode.MONTHLY,
            )
        )
    uow.audit.add(
        AuditEntry(
            name="INCOME_PLAN_UPDATED",
            entity="cost_center_plans",
            entity_id=plan.id,
            user_id=actor_id,
            old_value=json.dumps(
                {f"m{m:02d}_plan": format_euro(before[m]) for m in sorted(changed)},
                ensure_ascii=False,
            ),
            new_value=json.dumps(
                {f"m{m:02d}_plan": format_euro(new_values[m]) for m in sorted(changed)},
                ensure_ascii=False,
            ),
        )
    )
    return True
