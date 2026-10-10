"""Buchen, Ändern, Löschen und Stornieren (siehe Architekturvorgabe 2.2 bis 2.8, 5.2).

Jeder Vorgang läuft in einer Transaktion: Buchung, Buchungsstellen, Plan-Ist-Fortschreibung
bzw. Ansatz und Audit-Eintrag werden gemeinsam gespeichert oder gemeinsam verworfen.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

from meine_kasse.application.ports import Today, UnitOfWorkFactory, local_today
from meine_kasse.application.services.booking_control_service import load_or_create_control
from meine_kasse.domain.entities import (
    AuditEntry,
    Booking,
    BookingControl,
    BookingLeg,
    CostCenter,
    CostCenterPlan,
    MonthlyActual,
)
from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import NotFoundError, PeriodError, ValidationError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.booking_rules import (
    BookingEffects,
    Stelle,
    build_legs,
    effects_of,
    validate_amount,
)
from meine_kasse.domain.services.budget_rules import (
    BudgetPosition,
    check_actual_booking,
    check_budget_change,
    is_checked,
    validate_budget_transfer_allowed,
)
from meine_kasse.domain.services.period_rules import bookable_window, ensure_bookable
from meine_kasse.domain.value_objects.money import format_euro

_MAX_NAME_LENGTH = 200


class PeriodState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"


@dataclass(frozen=True, slots=True)
class PeriodStatus:
    state: PeriodState
    message: str


@dataclass(frozen=True, slots=True)
class CostCenterInfo:
    """Angaben zur Kostenstelle im Buchungsdialog (alle Beträge in Cent)."""

    cost_center_id: str
    year: int
    planning_active: bool
    annual_budget_cents: int
    movement_cents: int
    remaining_cents: int
    month_plan_cents: int
    month_movement_cents: int
    reserve_cents: int


@dataclass(frozen=True, slots=True)
class BookingView:
    """Zeile der Buchungsliste mit aufgelösten Bezeichnungen und Status."""

    id: str
    booking_date: date
    origin_date: date
    booking_type: BookingType
    entry_side: Side
    amount_cents: int
    leading_label: str
    second_label: str
    merchant: str
    booking_text: str
    fiscal_year: int
    fiscal_month: int
    is_closed: bool
    is_reversal: bool
    is_reversed: bool

    @property
    def can_edit(self) -> bool:
        return not (self.is_closed or self.is_reversal or self.is_reversed)

    @property
    def can_delete(self) -> bool:
        return not (self.is_closed or self.is_reversed)

    @property
    def can_reverse(self) -> bool:
        return not (self.is_reversal or self.is_reversed)


class BookingService:
    def __init__(self, uow_factory: UnitOfWorkFactory, today: Today = local_today) -> None:
        self._uow_factory = uow_factory
        self._today = today

    # Schreibende Vorgänge

    def post(
        self,
        *,
        booking_type: BookingType,
        entry_side: Side,
        amount_cents: int,
        booking_date: date,
        origin_date: date,
        leading: Stelle,
        second: Stelle,
        merchant: str = "",
        booking_text: str = "",
        actor_id: str,
    ) -> str:
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            booking = self._build(
                uow,
                control,
                booking_id=new_id(),
                booking_type=booking_type,
                entry_side=entry_side,
                amount_cents=amount_cents,
                booking_date=booking_date,
                origin_date=origin_date,
                leading=leading,
                second=second,
                merchant=merchant,
                booking_text=booking_text,
                created_by=actor_id,
                reversal_of_id=None,
            )
            self._apply(uow, control, effects_of(booking))
            uow.bookings.add(booking)
            uow.audit.add(_audit("BOOKING_CREATED", booking, actor_id, new=booking))
            uow.commit()
            return booking.id

    def update(
        self,
        booking_id: str,
        *,
        booking_type: BookingType,
        entry_side: Side,
        amount_cents: int,
        booking_date: date,
        origin_date: date,
        leading: Stelle,
        second: Stelle,
        merchant: str = "",
        booking_text: str = "",
        actor_id: str,
    ) -> None:
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            old = _get_booking(uow, booking_id)
            _ensure_open(uow, old)
            if old.reversal_of_id is not None:
                raise ValidationError(
                    "Ein Storno kann nicht geändert werden. Bitte löschen und neu buchen."
                )
            if uow.bookings.has_reversal(booking_id):
                raise ValidationError(
                    "Die Buchung wurde storniert. Bitte zuerst den Storno löschen."
                )
            new = self._build(
                uow,
                control,
                booking_id=booking_id,
                booking_type=booking_type,
                entry_side=entry_side,
                amount_cents=amount_cents,
                booking_date=booking_date,
                origin_date=origin_date,
                leading=leading,
                second=second,
                merchant=merchant,
                booking_text=booking_text,
                created_by=old.created_by_user_id,
                reversal_of_id=None,
            )
            self._apply(uow, control, effects_of(old).negated().combined(effects_of(new)))
            uow.bookings.update(new)
            uow.audit.add(_audit("BOOKING_UPDATED", new, actor_id, old=old, new=new))
            uow.commit()

    def delete(self, booking_id: str, *, actor_id: str) -> None:
        """Löscht eine Buchung in einem offenen Monat und nimmt ihre Wirkung zurück."""
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            old = _get_booking(uow, booking_id)
            _ensure_open(uow, old)
            if uow.bookings.has_reversal(booking_id):
                raise ValidationError(
                    "Die Buchung wurde storniert. Bitte zuerst den Storno löschen."
                )
            self._apply(uow, control, effects_of(old).negated())
            uow.bookings.delete(booking_id)
            uow.audit.add(_audit("BOOKING_DELETED", old, actor_id, old=old))
            uow.commit()

    def reverse(self, booking_id: str, *, booking_date: date, actor_id: str) -> str:
        """Storniert durch Minusbuchung auf derselben Seite (kein Seitentausch)."""
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            original = _get_booking(uow, booking_id)
            if original.reversal_of_id is not None:
                raise ValidationError("Ein Storno kann nicht erneut storniert werden.")
            if uow.bookings.has_reversal(booking_id):
                raise ValidationError("Die Buchung wurde bereits storniert.")
            text = f"Storno: {original.booking_text}".strip()
            reversal = self._build(
                uow,
                control,
                booking_id=new_id(),
                booking_type=original.booking_type,
                entry_side=original.entry_side,
                amount_cents=-original.amount_cents,
                booking_date=booking_date,
                origin_date=original.origin_date,
                leading=_stelle_of(original.legs[0]),
                second=_stelle_of(original.legs[1]),
                merchant=original.merchant,
                booking_text=text,
                created_by=actor_id,
                reversal_of_id=original.id,
                allow_inactive=True,
            )
            self._apply(uow, control, effects_of(reversal))
            uow.bookings.add(reversal)
            uow.audit.add(_audit("BOOKING_REVERSED", reversal, actor_id, new=reversal))
            uow.commit()
            return reversal.id

    def rebuild_projections(self, *, actor_id: str | None = None) -> None:
        """Baut Plan-Ist-Werte und Ansatzumbuchungen vollständig aus den Buchungen neu auf."""
        with self._uow_factory() as uow:
            totals = uow.bookings.cost_center_actual_totals()
            seen: set[tuple[str, int, int]] = set()
            for actual in uow.plans.list_actuals():
                key = (actual.cost_center_id, actual.year, actual.month)
                seen.add(key)
                debit, credit = totals.get(key, (0, 0))
                uow.plans.save_actual(replace(actual, debit_cents=debit, credit_cents=credit))
            for (cost_center_id, year, month), (debit, credit) in totals.items():
                if (cost_center_id, year, month) in seen:
                    continue
                uow.plans.save_actual(
                    MonthlyActual(
                        new_id(),
                        cost_center_id,
                        year,
                        month,
                        debit_cents=debit,
                        credit_cents=credit,
                    )
                )

            transfers = uow.bookings.budget_transfer_totals()
            planned: set[tuple[str, int]] = set()
            for plan in uow.plans.list_plans():
                plan_key = (plan.cost_center_id, plan.year)
                planned.add(plan_key)
                uow.plans.save_plan(replace(plan, budget_transfer_cents=transfers.get(plan_key, 0)))
            for (cost_center_id, year), total in transfers.items():
                if (cost_center_id, year) not in planned:
                    uow.plans.save_plan(
                        CostCenterPlan(new_id(), cost_center_id, year, budget_transfer_cents=total)
                    )
            uow.audit.add(
                AuditEntry(
                    name="PROJECTIONS_REBUILT",
                    entity="monthly_actuals",
                    entity_id=None,
                    user_id=actor_id,
                )
            )
            uow.commit()

    # Lesende Vorgänge

    def default_booking_date(self) -> date:
        """Heute, falls buchbar, sonst der erste Tag des aktuellen Buchungsmonats."""
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
        first, last = bookable_window(control.current_year, control.current_month)
        today = self._today()
        if first <= today <= last:
            return today
        return date(control.current_year, control.current_month, 1)

    def get_booking(self, booking_id: str) -> Booking:
        with self._uow_factory() as uow:
            return _get_booking(uow, booking_id)

    def cost_center_info(self, cost_center_id: str, booking_date: date) -> CostCenterInfo:
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            cost_center = _get_cost_center(uow, cost_center_id)
            year, month = booking_date.year, booking_date.month
            position = _position(uow, cost_center_id, year)
            actuals = uow.plans.actuals_for_year(cost_center_id, year)
            monthly = {plan.month: plan for plan in uow.plans.monthly_plans(cost_center_id, year)}
            return CostCenterInfo(
                cost_center_id=cost_center_id,
                year=year,
                planning_active=is_checked(control.planning_enabled, cost_center.kind),
                annual_budget_cents=position.annual_budget_cents,
                movement_cents=position.movement_cents,
                remaining_cents=position.remaining_cents,
                month_plan_cents=monthly[month].plan_cents if month in monthly else 0,
                month_movement_cents=sum(a.movement_cents for a in actuals if a.month == month),
                reserve_cents=sum(a.reserve_actual_cents for a in actuals),
            )

    def account_balance(self, account_id: str) -> int:
        """Saldo (Haben - Soll) aus den Buchungen. Ein Anfangsbestand ist noch nicht erfasst."""
        with self._uow_factory() as uow:
            if uow.accounts.get(account_id) is None:
                raise NotFoundError("Das Konto wurde nicht gefunden.")
            return uow.bookings.account_balance_cents(account_id)

    def period_status(self, booking_date: date) -> PeriodStatus:
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            closed_months = uow.closures.closed_months()
            closed_years = uow.closures.closed_years()
        label = f"{booking_date.month:02d}/{booking_date.year}"
        if (
            booking_date.year in closed_years
            or (booking_date.year, booking_date.month) in closed_months
        ):
            return PeriodStatus(PeriodState.CLOSED, f"Monat {label}: abgeschlossen (fix)")
        first, last = bookable_window(control.current_year, control.current_month)
        if not first <= booking_date <= last:
            return PeriodStatus(
                PeriodState.OUTSIDE_WINDOW,
                f"Monat {label}: offen, aber außerhalb des buchbaren Zeitraums",
            )
        return PeriodStatus(PeriodState.OPEN, f"Monat {label}: offen (frei)")

    def list_bookings(
        self, *, year: int | None = None, month: int | None = None
    ) -> Sequence[BookingView]:
        with self._uow_factory() as uow:
            bookings = uow.bookings.list_filtered(year, month)
            closed_months = uow.closures.closed_months()
            closed_years = uow.closures.closed_years()
            cost_centers = {c.id: f"{c.number} {c.name}" for c in uow.cost_centers.list_all()}
            accounts = {a.id: f"{a.number} {a.name}" for a in uow.accounts.list_all()}
            views = []
            for booking in bookings:
                labels = [
                    cost_centers.get(leg.cost_center_id or "", "")
                    or accounts.get(leg.account_id or "", "")
                    for leg in booking.legs
                ]
                views.append(
                    BookingView(
                        id=booking.id,
                        booking_date=booking.booking_date,
                        origin_date=booking.origin_date,
                        booking_type=booking.booking_type,
                        entry_side=booking.entry_side,
                        amount_cents=booking.amount_cents,
                        leading_label=labels[0],
                        second_label=labels[1],
                        merchant=booking.merchant,
                        booking_text=booking.booking_text,
                        fiscal_year=booking.fiscal_year,
                        fiscal_month=booking.fiscal_month,
                        is_closed=booking.fiscal_year in closed_years
                        or (booking.fiscal_year, booking.fiscal_month) in closed_months,
                        is_reversal=booking.reversal_of_id is not None,
                        is_reversed=uow.bookings.has_reversal(booking.id),
                    )
                )
            return views

    # Interne Bausteine

    def _build(
        self,
        uow: UnitOfWork,
        control: BookingControl,
        *,
        booking_id: str,
        booking_type: BookingType,
        entry_side: Side,
        amount_cents: int,
        booking_date: date,
        origin_date: date,
        leading: Stelle,
        second: Stelle,
        merchant: str,
        booking_text: str,
        created_by: str,
        reversal_of_id: str | None,
        allow_inactive: bool = False,
    ) -> Booking:
        validate_amount(amount_cents)
        ensure_bookable(
            booking_date,
            current_year=control.current_year,
            current_month=control.current_month,
            closed_months=uow.closures.closed_months(),
            closed_years=uow.closures.closed_years(),
        )
        first_leg, second_leg = build_legs(booking_type, entry_side, leading, second)

        cost_centers: list[CostCenter] = []
        for stelle in (leading, second):
            if stelle.kind is ObjectKind.COST_CENTER:
                cost_center = _get_cost_center(uow, stelle.id)
                if not cost_center.is_active and not allow_inactive:
                    raise ValidationError(f"Die Kostenstelle '{cost_center.name}' ist inaktiv.")
                cost_centers.append(cost_center)
            else:
                account = uow.accounts.get(stelle.id)
                if account is None:
                    raise NotFoundError("Das Konto wurde nicht gefunden.")
                if not account.is_active and not allow_inactive:
                    raise ValidationError(f"Das Konto '{account.name}' ist inaktiv.")
        if booking_type is BookingType.BUDGET_TRANSFER and reversal_of_id is None:
            validate_budget_transfer_allowed(
                planning_enabled=control.planning_enabled,
                kinds=(cost_centers[0].kind, cost_centers[1].kind),
            )

        name = (booking_text.strip() or merchant.strip())[:_MAX_NAME_LENGTH]
        return Booking(
            id=booking_id,
            name=name,
            origin_date=origin_date,
            booking_date=booking_date,
            booking_type=booking_type,
            entry_side=entry_side,
            amount_cents=amount_cents,
            merchant=merchant.strip(),
            booking_text=booking_text.strip(),
            reversal_of_id=reversal_of_id,
            fiscal_year=booking_date.year,
            fiscal_month=booking_date.month,
            created_by_user_id=created_by,
            legs=(
                _to_leg(first_leg.position, first_leg.side, leading),
                _to_leg(second_leg.position, second_leg.side, second),
            ),
        )

    def _apply(self, uow: UnitOfWork, control: BookingControl, effects: BookingEffects) -> None:
        """Prüft die Ansatzsperre und schreibt Ansatz und Ist-Summen fort."""
        for budget in effects.budgets:
            plan = uow.plans.get_plan(budget.cost_center_id, budget.year) or CostCenterPlan(
                new_id(), budget.cost_center_id, budget.year
            )
            if control.planning_enabled:
                check_budget_change(
                    _position(uow, budget.cost_center_id, budget.year), budget.delta_cents
                )
            uow.plans.save_plan(
                replace(plan, budget_transfer_cents=plan.budget_transfer_cents + budget.delta_cents)
            )

        for delta in effects.actuals:
            cost_center = _get_cost_center(uow, delta.cost_center_id)
            check_actual_booking(
                _position(uow, delta.cost_center_id, delta.year),
                delta.movement_delta_cents,
                planning_enabled=control.planning_enabled,
                kind=cost_center.kind,
            )
            actual = uow.plans.get_actual(delta.cost_center_id, delta.year, delta.month) or (
                MonthlyActual(new_id(), delta.cost_center_id, delta.year, delta.month)
            )
            uow.plans.save_actual(
                replace(
                    actual,
                    debit_cents=actual.debit_cents + delta.debit_delta_cents,
                    credit_cents=actual.credit_cents + delta.credit_delta_cents,
                )
            )


def _position(uow: UnitOfWork, cost_center_id: str, year: int) -> BudgetPosition:
    plan = uow.plans.get_plan(cost_center_id, year)
    movement = sum(
        actual.movement_cents for actual in uow.plans.actuals_for_year(cost_center_id, year)
    )
    distributed = sum(plan.plan_cents for plan in uow.plans.monthly_plans(cost_center_id, year))
    return BudgetPosition(
        annual_budget_cents=plan.effective_budget_cents if plan else 0,
        movement_cents=movement,
        distributed_cents=distributed,
    )


def _get_booking(uow: UnitOfWork, booking_id: str) -> Booking:
    booking = uow.bookings.get(booking_id)
    if booking is None:
        raise NotFoundError("Die Buchung wurde nicht gefunden.")
    return booking


def _get_cost_center(uow: UnitOfWork, cost_center_id: str) -> CostCenter:
    cost_center = uow.cost_centers.get(cost_center_id)
    if cost_center is None:
        raise NotFoundError("Die Kostenstelle wurde nicht gefunden.")
    return cost_center


def _ensure_open(uow: UnitOfWork, booking: Booking) -> None:
    """Eine Buchung ist erst mit dem Abschluss ihres Monats unveränderbar."""
    if (
        booking.fiscal_year in uow.closures.closed_years()
        or (
            booking.fiscal_year,
            booking.fiscal_month,
        )
        in uow.closures.closed_months()
    ):
        raise PeriodError(
            f"Der Monat {booking.fiscal_month:02d}/{booking.fiscal_year} ist abgeschlossen. "
            "Korrekturen sind nur durch eine Gegenbuchung (Storno) möglich."
        )


def _to_leg(position: int, side: Side, stelle: Stelle) -> BookingLeg:
    is_cost_center = stelle.kind is ObjectKind.COST_CENTER
    return BookingLeg(
        position=position,
        side=side,
        cost_center_id=stelle.id if is_cost_center else None,
        account_id=None if is_cost_center else stelle.id,
    )


def _stelle_of(leg: BookingLeg) -> Stelle:
    if leg.cost_center_id is not None:
        return Stelle(ObjectKind.COST_CENTER, leg.cost_center_id)
    assert leg.account_id is not None
    return Stelle(ObjectKind.ACCOUNT, leg.account_id)


def _summary(booking: Booking) -> str:
    return json.dumps(
        {
            "booking_date": booking.booking_date.isoformat(),
            "booking_type": booking.booking_type.value,
            "entry_side": booking.entry_side.value,
            "amount": format_euro(booking.amount_cents),
        },
        ensure_ascii=False,
    )


def _audit(
    name: str,
    booking: Booking,
    actor_id: str,
    *,
    old: Booking | None = None,
    new: Booking | None = None,
) -> AuditEntry:
    return AuditEntry(
        name=name,
        entity="bookings",
        entity_id=booking.id,
        user_id=actor_id,
        old_value=None if old is None else _summary(old),
        new_value=None if new is None else _summary(new),
    )
