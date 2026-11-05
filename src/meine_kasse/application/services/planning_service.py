"""Kostenstellenplanung: Haushaltsansatz, Monatswerte, Rückstellungen (Architekturvorgabe 2.7,
2.8, 2.12).

- Der Basisansatz ist bei aktiver Planung fix und ändert sich dann nur per Ansatzumbuchung. Das
  gilt nicht für Folgejahre des Buchungsjahres: Sie werden vorab geplant.
- Die Verteilung auf Monate läuft hier, ohne Buchung, solange die Summe im Jahresansatz bleibt.
- Die Zuführungen zur Rückstellung werden maschinell verteilt. Manuell gesetzte Monate bleiben,
  abgeschlossene Monate sind gesperrt.
- Entlastung und Vortrag der Rückstellung sind Projektionen aus Plan und Ist.
- Jede Änderung wird protokolliert.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace

from meine_kasse.application.ports import Today, UnitOfWorkFactory, local_today
from meine_kasse.application.services.booking_control_service import load_or_create_control
from meine_kasse.application.services.income_planning import (
    IncomeMonthInput,
    IncomeView,
    build_income_view,
    get_income_cost_center,
    save_income_plan,
)
from meine_kasse.application.services.liquidity_planning import LiquidityView, build_liquidity_view
from meine_kasse.application.services.reserve_projection import apply_projection
from meine_kasse.domain.entities import AuditEntry, CostCenter, CostCenterPlan, MonthlyPlan
from meine_kasse.domain.enums import CostCenterKind, PlanMode
from meine_kasse.domain.errors import NotFoundError, PeriodError, ValidationError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.planning_rules import (
    MONTHS,
    check_distribution,
    check_reserve_distribution,
    validate_month_amounts,
    validate_plan_amounts,
)
from meine_kasse.domain.services.reserve_rules import (
    ReserveYear,
    compute_reserve_outlook,
    distribute_reserve,
    plan_shortfalls,
)
from meine_kasse.domain.value_objects.money import format_euro

_FIXED_BASE_MESSAGE = (
    "Der Haushaltsansatz ist bei aktiver Planung fix. "
    "Änderungen sind nur durch Ansatzumbuchung möglich."
)

_CARRY_IN_LOCKED_MESSAGE = (
    "Der Januar {year} ist abgeschlossen. Der Rückstellungsvortrag kann nicht mehr geändert werden."
)


@dataclass(frozen=True, slots=True)
class MonthPlanInput:
    """Eingabe eines Planmonats.

    `reserve_plan_cents=None` bedeutet: Die Zuführung wird maschinell berechnet. Ein Betrag
    setzt sie manuell und schützt sie vor der maschinellen Verteilung.
    """

    month: int
    plan_cents: int
    reserve_plan_cents: int | None = None
    plan_mode: PlanMode = PlanMode.MONTHLY


@dataclass(frozen=True, slots=True)
class PlanMonthView:
    """Ein Monat der Planung mit Ist-Werten (Soll und Haben getrennt) und Status."""

    month: int
    plan_cents: int
    reserve_plan_cents: int
    reserve_is_manual: bool
    reserve_release_cents: int
    reserve_balance_cents: int
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
    reserve_carry_in_editable: bool
    reserve_carry_out_cents: int
    reserve_notices: tuple[str, ...]
    months: tuple[PlanMonthView, ...]
    is_future_year: bool = False
    reserve_carry_in_manual: bool = False
    reserve_carry_in_derivable: bool = False

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
        return not self.year_closed and (not self.planning_enabled or self.is_future_year)


@dataclass(frozen=True, slots=True)
class ReservePreview:
    """Ergebnis der maschinellen Rückstellungsrechnung für die Anzeige im Planungsdialog."""

    reserve_plan: dict[int, int]
    manual: frozenset[int]
    release: dict[int, int]
    balance: dict[int, int]
    carry_in_cents: int
    carry_out_cents: int
    notices: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Resolved:
    plan_cents: dict[int, int]
    reserve_plan: dict[int, int]
    manual: frozenset[int]
    modes: dict[int, PlanMode]
    carry_in_cents: int
    carry_in_manual: bool
    effective_budget_cents: int
    year_result: ReserveYear
    notices: tuple[str, ...]


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

    def list_income_cost_centers(self) -> Sequence[CostCenter]:
        """Aktive Einnahmen-Kostenstellen (Art `INCOME`)."""
        with self._uow_factory() as uow:
            return [
                cost_center
                for cost_center in uow.cost_centers.list_all()
                if cost_center.is_active and cost_center.kind is CostCenterKind.INCOME
            ]

    def get_income_view(self, cost_center_id: str, year: int) -> IncomeView:
        with self._uow_factory() as uow:
            cost_center = get_income_cost_center(uow, cost_center_id)
            return build_income_view(uow, cost_center, year)

    def save_income_plan(
        self,
        cost_center_id: str,
        year: int,
        *,
        months: Sequence[IncomeMonthInput],
        actor_id: str,
    ) -> None:
        """Speichert die erwartete Einnahme je Monat einer Einnahmen-Kostenstelle."""
        with self._uow_factory() as uow:
            cost_center = get_income_cost_center(uow, cost_center_id)
            if save_income_plan(uow, cost_center, year, months, actor_id):
                uow.commit()

    def get_liquidity_view(self, year: int) -> LiquidityView:
        """Monatsvergleich Einnahmen gegen Liquiditätsbedarf (Rückstellungen und Zahlungen)."""
        with self._uow_factory() as uow:
            return build_liquidity_view(uow, year)

    def get_plan_view(self, cost_center_id: str, year: int) -> PlanView:
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            _get_planned_cost_center(uow, cost_center_id)
            plan = uow.plans.get_plan(cost_center_id, year)
            monthly = {item.month: item for item in uow.plans.monthly_plans(cost_center_id, year)}
            actuals = {a.month: a for a in uow.plans.actuals_for_year(cost_center_id, year)}
            closed_months = uow.closures.closed_months()
            year_closed = year in uow.closures.closed_years()
            carry_in, carry_in_manual = _resolve_carry_in(
                uow, cost_center_id, year, None, strict=False
            )
            closed = {m for m in MONTHS if year_closed or (year, m) in closed_months}
            outlook = compute_reserve_outlook(
                carry_in,
                {m: p.reserve_plan_cents for m, p in monthly.items()},
                {m: p.plan_cents for m, p in monthly.items()},
                {m: a.movement_cents for m, a in actuals.items()},
                closed,
            )
            months = []
            for month in MONTHS:
                planned = monthly.get(month)
                actual = actuals.get(month)
                months.append(
                    PlanMonthView(
                        month=month,
                        plan_cents=planned.plan_cents if planned else 0,
                        reserve_plan_cents=planned.reserve_plan_cents if planned else 0,
                        reserve_is_manual=planned.reserve_is_manual if planned else False,
                        reserve_release_cents=outlook.release[month],
                        reserve_balance_cents=outlook.balance[month],
                        plan_mode=planned.plan_mode if planned else PlanMode.MONTHLY,
                        debit_cents=actual.debit_cents if actual else 0,
                        credit_cents=actual.credit_cents if actual else 0,
                        is_closed=year_closed or (year, month) in closed_months,
                    )
                )
            effective = plan.effective_budget_cents if plan else 0
            return PlanView(
                cost_center_id=cost_center_id,
                year=year,
                planning_enabled=control.planning_enabled,
                year_closed=year_closed,
                base_budget_cents=plan.base_budget_cents if plan else 0,
                budget_transfer_cents=plan.budget_transfer_cents if plan else 0,
                reserve_carry_in_cents=carry_in,
                reserve_carry_in_editable=_carry_in_editable(uow, cost_center_id, year),
                reserve_carry_out_cents=outlook.carry_out_cents,
                reserve_notices=_notices(
                    year,
                    {item.month: item.plan_cents for item in months},
                    {item.month: item.reserve_plan_cents for item in months},
                    carry_in,
                    effective,
                ),
                months=tuple(months),
                is_future_year=year > control.current_year,
                reserve_carry_in_manual=carry_in_manual,
                reserve_carry_in_derivable=uow.plans.get_plan(cost_center_id, year - 1) is not None,
            )

    def get_unplanned_view(self, cost_center_id: str, year: int) -> PlanView:
        """Ist-Werte einer Kostenstelle ohne Plan für die Auswertung (ohne Ansatz, ohne Plan)."""
        with self._uow_factory() as uow:
            cost_center = uow.cost_centers.get(cost_center_id)
            if cost_center is None:
                raise NotFoundError("Die Kostenstelle wurde nicht gefunden.")
            if cost_center.kind is not CostCenterKind.WITHOUT_PLAN:
                raise ValidationError("Das ist keine Kostenstelle ohne Plan.")
            actuals = {a.month: a for a in uow.plans.actuals_for_year(cost_center_id, year)}
            closed_months = uow.closures.closed_months()
            year_closed = year in uow.closures.closed_years()
            months = tuple(
                PlanMonthView(
                    month=month,
                    plan_cents=0,
                    reserve_plan_cents=0,
                    reserve_is_manual=False,
                    reserve_release_cents=0,
                    reserve_balance_cents=0,
                    plan_mode=PlanMode.MONTHLY,
                    debit_cents=actuals[month].debit_cents if month in actuals else 0,
                    credit_cents=actuals[month].credit_cents if month in actuals else 0,
                    is_closed=year_closed or (year, month) in closed_months,
                )
                for month in MONTHS
            )
            return PlanView(
                cost_center_id=cost_center_id,
                year=year,
                planning_enabled=False,
                year_closed=year_closed,
                base_budget_cents=0,
                budget_transfer_cents=0,
                reserve_carry_in_cents=0,
                reserve_carry_in_editable=False,
                reserve_carry_out_cents=0,
                reserve_notices=(),
                months=months,
            )

    def preview_reserve(
        self,
        cost_center_id: str,
        year: int,
        *,
        base_budget_cents: int,
        carry_in_cents: int | None,
        months: Sequence[MonthPlanInput],
        to_payment_targets: bool = False,
        carry_in_automatic: bool = False,
    ) -> ReservePreview:
        """Berechnet die Rückstellung für die Eingaben, ohne zu speichern (Live-Anzeige).

        Mit `to_payment_targets` sind die maschinellen Zuführungen auf die Zahlungsmonate
        ausgerichtet (Konstellation Zahlungsziel), sonst gleichmäßig verteilt. Mit
        `carry_in_automatic` folgt der Vortrag wieder dem Vorjahr.
        """
        validate_plan_amounts(base_cents=base_budget_cents, carry_in_cents=carry_in_cents or 0)
        for item in months:
            validate_month_amounts(item.month, item.plan_cents, item.reserve_plan_cents)
        with self._uow_factory() as uow:
            _get_planned_cost_center(uow, cost_center_id)
            resolved = _resolve(
                uow,
                cost_center_id,
                year,
                base_budget_cents=base_budget_cents,
                carry_in_cents=carry_in_cents,
                months=months,
                strict=False,
                to_payment_targets=to_payment_targets,
                carry_in_automatic=carry_in_automatic,
            )
        result = resolved.year_result
        return ReservePreview(
            reserve_plan=resolved.reserve_plan,
            manual=resolved.manual,
            release=result.release,
            balance=result.balance,
            carry_in_cents=resolved.carry_in_cents,
            carry_out_cents=result.carry_out_cents,
            notices=resolved.notices,
        )

    def refresh_reserves(self) -> None:
        """Rechnet Entlastung und Vorträge aller Kostenstellen neu (z. B. nach einer Migration)."""
        with self._uow_factory() as uow:
            changed = False
            for cost_center_id in sorted({plan.cost_center_id for plan in uow.plans.list_plans()}):
                changed = apply_projection(uow, cost_center_id, 0) or changed
            if changed:
                uow.audit.add(
                    AuditEntry(
                        name="RESERVES_REFRESHED",
                        entity="monthly_actuals",
                        entity_id=None,
                        user_id=None,
                    )
                )
                uow.commit()

    def save_plan(
        self,
        cost_center_id: str,
        year: int,
        *,
        base_budget_cents: int,
        reserve_carry_in_cents: int | None = None,
        months: Sequence[MonthPlanInput],
        actor_id: str,
        carry_in_automatic: bool = False,
    ) -> None:
        """Speichert den Plan.

        Der Rückstellungsvortrag folgt dem Vorjahresplan, kann aber bis zum Abschluss des Januars
        von Hand überschrieben werden. `carry_in_automatic` nimmt die Überschreibung zurück.
        """
        validate_plan_amounts(
            base_cents=base_budget_cents, carry_in_cents=reserve_carry_in_cents or 0
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
            if (
                control.planning_enabled
                and year <= control.current_year
                and base_budget_cents != plan.base_budget_cents
            ):
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

            resolved = _resolve(
                uow,
                cost_center_id,
                year,
                base_budget_cents=base_budget_cents,
                carry_in_cents=reserve_carry_in_cents,
                months=months,
                strict=True,
                carry_in_automatic=carry_in_automatic,
            )
            new_plan = replace(
                plan,
                base_budget_cents=base_budget_cents,
                reserve_carry_in_cents=resolved.carry_in_cents,
                reserve_carry_in_is_manual=resolved.carry_in_manual,
                reserve_carry_out_cents=resolved.year_result.carry_out_cents,
            )
            check_distribution(new_plan.effective_budget_cents, sum(resolved.plan_cents.values()))
            check_reserve_distribution(
                new_plan.effective_budget_cents, sum(resolved.reserve_plan.values())
            )
            new_months = dict(existing_months)
            for month in MONTHS:
                current = existing_months.get(month)
                candidate = MonthlyPlan(
                    id=current.id if current else new_id(),
                    cost_center_plan_id=new_plan.id,
                    month=month,
                    plan_cents=resolved.plan_cents[month],
                    reserve_plan_cents=resolved.reserve_plan[month],
                    plan_mode=resolved.modes[month],
                    reserve_is_manual=month in resolved.manual,
                )
                if current is None and not _has_content(candidate):
                    continue
                new_months[month] = candidate

            before = _snapshot(existing_plan, existing_months)
            after = _snapshot(new_plan, new_months)
            changed = {key for key in after if before.get(key) != after[key]}
            if not changed and existing_plan is not None:
                return

            uow.plans.save_plan(new_plan)
            for month, candidate in new_months.items():
                if existing_months.get(month) != candidate:
                    uow.plans.save_monthly_plan(candidate)
            apply_projection(uow, cost_center_id, year)
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
    if cost_center.kind is CostCenterKind.INCOME:
        raise ValidationError("Einnahmen-Kostenstellen werden in der Einnahmenplanung geplant.")
    if cost_center.kind is not CostCenterKind.STANDARD:
        raise ValidationError("Für Kostenstellen ohne Plan gibt es keine Planung.")
    return cost_center


def _has_content(item: MonthlyPlan) -> bool:
    return bool(
        item.plan_cents
        or item.reserve_plan_cents
        or item.reserve_is_manual
        or item.plan_mode is not PlanMode.MONTHLY
    )


def _differs(current: MonthlyPlan | None, item: MonthPlanInput) -> bool:
    """Ändert die Eingabe den Monat? Eine maschinelle Zuführung (None) gilt als unverändert."""
    plan_cents = current.plan_cents if current else 0
    reserve = current.reserve_plan_cents if current else 0
    mode = current.plan_mode if current else PlanMode.MONTHLY
    return (
        item.plan_cents != plan_cents
        or (item.reserve_plan_cents is not None and item.reserve_plan_cents != reserve)
        or item.plan_mode is not mode
    )


def _carry_in_editable(uow: UnitOfWork, cost_center_id: str, year: int) -> bool:
    """Der Vortrag ist bis zum Abschluss des Januars änderbar (danach fix)."""
    return year not in uow.closures.closed_years() and (year, 1) not in uow.closures.closed_months()


def _notices(
    year: int,
    plan_cents: dict[int, int],
    reserve_plan: dict[int, int],
    carry_in_cents: int,
    effective_budget_cents: int,
) -> tuple[str, ...]:
    notices = [
        f"Monat {month:02d}/{year}: Die Rückstellung deckt die geplante Zahlung nicht, "
        f"es fehlen {format_euro(shortfall)}."
        for month, shortfall in plan_shortfalls(carry_in_cents, reserve_plan, plan_cents).items()
    ]
    total = sum(reserve_plan.values())
    if total > max(0, effective_budget_cents):
        notices.append(
            f"Die Zuführungen ({format_euro(total)}) übersteigen den Jahresansatz "
            f"({format_euro(effective_budget_cents)}). Bitte die Rückstellung neu verteilen."
        )
    return tuple(notices)


def _resolve(
    uow: UnitOfWork,
    cost_center_id: str,
    year: int,
    *,
    base_budget_cents: int,
    carry_in_cents: int | None,
    months: Sequence[MonthPlanInput],
    strict: bool,
    to_payment_targets: bool = False,
    carry_in_automatic: bool = False,
) -> _Resolved:
    """Bestimmt Planwerte, Zuführungen (maschinell oder manuell) und Rückstellungsrechnung.

    Abgeschlossene Monate behalten ihre Werte. Mit `strict` werden unzulässige Vortragsänderungen
    abgelehnt, sonst (Vorschau) bleibt der abgeleitete bzw. gespeicherte Vortrag. Mit
    `to_payment_targets` werden die maschinellen Zuführungen auf die Zahlungsmonate ausgerichtet.
    """
    plan = uow.plans.get_plan(cost_center_id, year)
    existing = {item.month: item for item in uow.plans.monthly_plans(cost_center_id, year)}
    closed_months = uow.closures.closed_months()
    year_closed = year in uow.closures.closed_years()
    inputs = {item.month: item for item in months}

    plan_cents: dict[int, int] = {}
    modes: dict[int, PlanMode] = {}
    fixed: dict[int, int] = {}
    manual: set[int] = set()
    free: list[int] = []
    for month in MONTHS:
        current = existing.get(month)
        modes[month] = current.plan_mode if current else PlanMode.MONTHLY
        if year_closed or (year, month) in closed_months:
            plan_cents[month] = current.plan_cents if current else 0
            fixed[month] = current.reserve_plan_cents if current else 0
            if current is not None and current.reserve_is_manual:
                manual.add(month)
            continue
        item = inputs.get(month)
        if item is None:
            keep_manual = current is not None and current.reserve_is_manual
            item = MonthPlanInput(
                month,
                current.plan_cents if current else 0,
                current.reserve_plan_cents if current is not None and keep_manual else None,
                modes[month],
            )
        plan_cents[month] = item.plan_cents
        modes[month] = item.plan_mode
        if item.reserve_plan_cents is None:
            free.append(month)
        else:
            fixed[month] = item.reserve_plan_cents
            manual.add(month)

    carry_in, carry_in_manual = _resolve_carry_in(
        uow, cost_center_id, year, carry_in_cents, strict=strict, automatic=carry_in_automatic
    )
    effective = base_budget_cents + (plan.budget_transfer_cents if plan else 0)
    reserve_plan = distribute_reserve(
        budget_cents=effective,
        carry_in_cents=carry_in,
        plan_cents=plan_cents,
        fixed=fixed,
        free_months=free,
        to_payment_targets=to_payment_targets,
    )
    movement = {a.month: a.movement_cents for a in uow.plans.actuals_for_year(cost_center_id, year)}
    closed = {m for m in MONTHS if year_closed or (year, m) in closed_months}
    return _Resolved(
        plan_cents=plan_cents,
        reserve_plan=reserve_plan,
        manual=frozenset(manual),
        modes=modes,
        carry_in_cents=carry_in,
        carry_in_manual=carry_in_manual,
        effective_budget_cents=effective,
        year_result=compute_reserve_outlook(carry_in, reserve_plan, plan_cents, movement, closed),
        notices=_notices(year, plan_cents, reserve_plan, carry_in, effective),
    )


def _resolve_carry_in(
    uow: UnitOfWork,
    cost_center_id: str,
    year: int,
    requested: int | None,
    *,
    strict: bool,
    automatic: bool = False,
) -> tuple[int, bool]:
    """Bestimmt den Vortrag und ob er von Hand gesetzt ist.

    Mit Vorjahresplan folgt der Vortrag dem Vorjahr, bis er überschrieben wird (`requested`).
    `automatic` nimmt die Überschreibung zurück. Nach Abschluss des Januars ist er fix.
    """
    plan = uow.plans.get_plan(cost_center_id, year)
    stored = plan.reserve_carry_in_cents if plan else 0
    previous = uow.plans.get_plan(cost_center_id, year - 1)
    editable = _carry_in_editable(uow, cost_center_id, year)
    if previous is None:
        if requested is None or requested == stored:
            return stored, False
        if not editable:
            if strict:
                raise PeriodError(_CARRY_IN_LOCKED_MESSAGE.format(year=year))
            return stored, False
        return requested, False

    derived = previous.reserve_carry_out_cents
    manual = plan.reserve_carry_in_is_manual if plan else False
    current = stored if manual else derived
    if not editable:
        if strict and ((automatic and manual) or requested not in (None, current)):
            raise PeriodError(_CARRY_IN_LOCKED_MESSAGE.format(year=year))
        return current, manual
    if automatic:
        return derived, False
    if requested is None or requested == current:
        return current, manual
    return requested, True


def _snapshot(plan: CostCenterPlan | None, months: dict[int, MonthlyPlan]) -> dict[str, str]:
    values = {
        "base_budget": format_euro(plan.base_budget_cents if plan else 0),
        "reserve_carry_in": format_euro(plan.reserve_carry_in_cents if plan else 0),
        "reserve_carry_out": format_euro(plan.reserve_carry_out_cents if plan else 0),
        "reserve_carry_in_manual": (
            "manuell" if plan is not None and plan.reserve_carry_in_is_manual else "automatisch"
        ),
    }
    for month in MONTHS:
        item = months.get(month)
        values[f"m{month:02d}_plan"] = format_euro(item.plan_cents if item else 0)
        values[f"m{month:02d}_reserve"] = format_euro(item.reserve_plan_cents if item else 0)
        values[f"m{month:02d}_reserve_manual"] = (
            "manuell" if item is not None and item.reserve_is_manual else "maschinell"
        )
        values[f"m{month:02d}_mode"] = (item.plan_mode if item else PlanMode.MONTHLY).value
    return values
