"""Monats- und Jahresabschluss mit Signatur (siehe Architekturvorgabe 2.5, 5.3, 6.4).

Ein abgeschlossener Monat ist unveränderbar. Korrekturen erfolgen nur durch Storno in einem
offenen Zeitraum. Die Abschlüsse gehen lückenlos nacheinander.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

from meine_kasse.application.ports import Today, UnitOfWorkFactory, local_today
from meine_kasse.application.services.booking_control_service import load_or_create_control
from meine_kasse.domain.entities import AuditEntry, ClosureReopening, PeriodClosure, YearClosure
from meine_kasse.domain.enums import ClosureKind
from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.closing_rules import (
    MONTHS_PER_YEAR,
    ClosureRef,
    latest_closure,
    month_signature,
    next_period,
    projection_mismatches,
    validate_reopen_reason,
    year_signature,
)
from meine_kasse.domain.value_objects.money import format_euro


@dataclass(frozen=True, slots=True)
class MonthClosureView:
    month: int
    is_closed: bool
    is_current: bool
    closed_on: date | None
    signature: str | None


@dataclass(frozen=True, slots=True)
class ClosingOverview:
    year: int
    current_year: int
    current_month: int
    months: tuple[MonthClosureView, ...]
    year_closed: bool
    year_closed_on: date | None
    year_signature: str | None
    month_blocker: str | None
    year_blocker: str | None
    reopen_target: ClosureRef | None

    @property
    def can_close_month(self) -> bool:
        return self.month_blocker is None

    @property
    def can_close_year(self) -> bool:
        return self.year_blocker is None

    @property
    def can_reopen(self) -> bool:
        return self.reopen_target is not None


@dataclass(frozen=True, slots=True)
class ReopeningView:
    """Eintrag der Wiedereröffnungs-Historie mit aufgelösten Anwendernamen."""

    ref: ClosureRef
    reopened_on: date
    reopened_by: str
    reason: str
    previous_closed_on: date
    previous_closed_by: str
    signature_was_valid: bool


@dataclass(frozen=True, slots=True)
class MonthClosureResult:
    year: int
    month: int
    signature: str
    next_year: int
    next_month: int


@dataclass(frozen=True, slots=True)
class ClosureCheck:
    """Ergebnis der Integritätsprüfung für einen Abschluss."""

    year: int
    month: int | None
    ok: bool
    message: str


class ClosingService:
    def __init__(self, uow_factory: UnitOfWorkFactory, today: Today = local_today) -> None:
        self._uow_factory = uow_factory
        self._today = today

    def get_overview(self, year: int) -> ClosingOverview:
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            closures = {c.month: c for c in uow.closures.list_months() if c.year == year}
            year_closure = next((c for c in uow.closures.list_years() if c.year == year), None)
            current = (control.current_year, control.current_month)
            months = tuple(
                MonthClosureView(
                    month=month,
                    is_closed=month in closures,
                    is_current=current == (year, month),
                    closed_on=closures[month].closed_on if month in closures else None,
                    signature=closures[month].signature if month in closures else None,
                )
                for month in range(1, MONTHS_PER_YEAR + 1)
            )
            return ClosingOverview(
                year=year,
                current_year=control.current_year,
                current_month=control.current_month,
                months=months,
                year_closed=year_closure is not None,
                year_closed_on=year_closure.closed_on if year_closure else None,
                year_signature=year_closure.signature if year_closure else None,
                month_blocker=_month_blocker(uow, current),
                year_blocker=_year_blocker(year, closures, year_closure is not None),
                reopen_target=latest_closure(
                    uow.closures.closed_months(), uow.closures.closed_years()
                ),
            )

    def close_month(self, *, actor_id: str) -> MonthClosureResult:
        """Schließt den aktuellen Buchungsmonat ab und rückt den Buchungsmonat weiter."""
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            period = (control.current_year, control.current_month)
            blocker = _month_blocker(uow, period)
            if blocker is not None:
                raise ValidationError(blocker)
            year, month = period
            problems = _consistency_problems(uow, year, month)
            if problems:
                raise ValidationError(
                    f"Der Monat {month:02d}/{year} kann nicht abgeschlossen werden:\n- "
                    + "\n- ".join(problems)
                )
            signature = _signature_of_month(uow, year, month)
            uow.closures.add_month(
                PeriodClosure(new_id(), year, month, self._today(), actor_id, signature)
            )
            next_year, next_month = next_period(year, month)
            uow.booking_control.update(
                replace(
                    control,
                    last_closed_year=year,
                    last_closed_month=month,
                    current_year=next_year,
                    current_month=next_month,
                )
            )
            uow.audit.add(
                AuditEntry(
                    name="MONTH_CLOSED",
                    entity="period_closures",
                    entity_id=None,
                    user_id=actor_id,
                    new_value=f"{month:02d}/{year} {signature[:16]}",
                )
            )
            uow.commit()
            return MonthClosureResult(year, month, signature, next_year, next_month)

    def close_year(self, year: int, *, actor_id: str) -> str:
        """Schließt ein Jahr ab, wenn alle zwölf Monate abgeschlossen und unverändert sind."""
        with self._uow_factory() as uow:
            load_or_create_control(uow, self._today)
            closures = {c.month: c for c in uow.closures.list_months() if c.year == year}
            blocker = _year_blocker(year, closures, year in uow.closures.closed_years())
            if blocker is not None:
                raise ValidationError(blocker)
            for month, closure in closures.items():
                if _signature_of_month(uow, year, month) != closure.signature:
                    raise ValidationError(
                        f"Die Signatur des Monats {month:02d}/{year} stimmt nicht mehr. "
                        "Das Jahr kann nicht abgeschlossen werden."
                    )
            signature = year_signature(year, {m: c.signature for m, c in closures.items()})
            uow.closures.add_year(YearClosure(new_id(), year, self._today(), actor_id, signature))
            uow.audit.add(
                AuditEntry(
                    name="YEAR_CLOSED",
                    entity="year_closures",
                    entity_id=None,
                    user_id=actor_id,
                    new_value=f"{year} {signature[:16]}",
                )
            )
            uow.commit()
            return signature

    def reopen_month(self, year: int, month: int, *, reason: str, actor_id: str) -> None:
        """Öffnet einen Monatsabschluss wieder. Nur der zuletzt liegende Abschluss ist erlaubt.

        Der Abschluss entfällt, der Buchungsmonat springt auf diesen Monat zurück. Das
        Wiedereröffnen wird mit Begründung und verworfener Signatur dauerhaft dokumentiert.
        """
        reason = validate_reopen_reason(reason)
        target = ClosureRef(ClosureKind.MONTH, year, month)
        with self._uow_factory() as uow:
            control = load_or_create_control(uow, self._today)
            _require_latest(uow, target)
            closure = next(
                c for c in uow.closures.list_months() if (c.year, c.month) == (year, month)
            )
            was_valid = _signature_of_month(uow, year, month) == closure.signature

            uow.closures.delete_month(year, month)
            uow.closures.add_reopening(
                ClosureReopening(
                    id=new_id(),
                    kind=ClosureKind.MONTH,
                    year=year,
                    month=month,
                    reopened_on=self._today(),
                    reopened_by_user_id=actor_id,
                    reason=reason,
                    previous_signature=closure.signature,
                    previous_closed_on=closure.closed_on,
                    previous_closed_by_user_id=closure.closed_by_user_id,
                    signature_was_valid=was_valid,
                )
            )
            remaining = uow.closures.list_months()
            last = max(((c.year, c.month) for c in remaining), default=None)
            uow.booking_control.update(
                replace(
                    control,
                    last_closed_year=last[0] if last else None,
                    last_closed_month=last[1] if last else None,
                    current_year=year,
                    current_month=month,
                )
            )
            uow.audit.add(
                _reopen_audit("MONTH_REOPENED", target, closure.signature, reason, actor_id)
            )
            uow.commit()

    def reopen_year(self, year: int, *, reason: str, actor_id: str) -> None:
        """Öffnet einen Jahresabschluss wieder. Nur der zuletzt liegende Abschluss ist erlaubt."""
        reason = validate_reopen_reason(reason)
        target = ClosureRef(ClosureKind.YEAR, year)
        with self._uow_factory() as uow:
            load_or_create_control(uow, self._today)
            _require_latest(uow, target)
            closure = next(c for c in uow.closures.list_years() if c.year == year)
            months = {c.month: c for c in uow.closures.list_months() if c.year == year}
            was_valid = all(
                _signature_of_month(uow, year, month) == item.signature
                for month, item in months.items()
            )
            try:
                was_valid = was_valid and (
                    year_signature(year, {m: c.signature for m, c in months.items()})
                    == closure.signature
                )
            except ValidationError:
                was_valid = False

            uow.closures.delete_year(year)
            uow.closures.add_reopening(
                ClosureReopening(
                    id=new_id(),
                    kind=ClosureKind.YEAR,
                    year=year,
                    month=None,
                    reopened_on=self._today(),
                    reopened_by_user_id=actor_id,
                    reason=reason,
                    previous_signature=closure.signature,
                    previous_closed_on=closure.closed_on,
                    previous_closed_by_user_id=closure.closed_by_user_id,
                    signature_was_valid=was_valid,
                )
            )
            uow.audit.add(
                _reopen_audit("YEAR_REOPENED", target, closure.signature, reason, actor_id)
            )
            uow.commit()

    def list_reopenings(self) -> Sequence[ReopeningView]:
        """Historie aller Wiedereröffnungen, die jüngste zuerst."""
        with self._uow_factory() as uow:
            names: dict[str, str] = {}

            def name_of(user_id: str) -> str:
                if user_id not in names:
                    user = uow.users.get(user_id)
                    names[user_id] = user.display_name if user else user_id
                return names[user_id]

            views = [
                ReopeningView(
                    ref=ClosureRef(item.kind, item.year, item.month),
                    reopened_on=item.reopened_on,
                    reopened_by=name_of(item.reopened_by_user_id),
                    reason=item.reason,
                    previous_closed_on=item.previous_closed_on,
                    previous_closed_by=name_of(item.previous_closed_by_user_id),
                    signature_was_valid=item.signature_was_valid,
                )
                for item in uow.closures.list_reopenings()
            ]
            return list(reversed(views))

    def verify_closures(self) -> Sequence[ClosureCheck]:
        """Berechnet alle Signaturen neu. Abweichungen weisen auf nachträgliche Änderungen hin."""
        with self._uow_factory() as uow:
            results: list[ClosureCheck] = []
            months = uow.closures.list_months()
            for closure in months:
                ok = _signature_of_month(uow, closure.year, closure.month) == closure.signature
                label = f"{closure.month:02d}/{closure.year}"
                results.append(
                    ClosureCheck(
                        closure.year,
                        closure.month,
                        ok,
                        f"Monat {label}: " + ("Signatur gültig" if ok else "Signatur ABWEICHEND"),
                    )
                )
            for year_closure in uow.closures.list_years():
                by_month = {c.month: c.signature for c in months if c.year == year_closure.year}
                try:
                    ok = year_signature(year_closure.year, by_month) == year_closure.signature
                except ValidationError:
                    ok = False
                results.append(
                    ClosureCheck(
                        year_closure.year,
                        None,
                        ok,
                        f"Jahr {year_closure.year}: "
                        + ("Signatur gültig" if ok else "Signatur ABWEICHEND"),
                    )
                )
            return results


def _require_latest(uow: UnitOfWork, target: ClosureRef) -> None:
    """Abschlüsse dürfen nur in umgekehrter Reihenfolge wiedereröffnet werden."""
    closed_months = uow.closures.closed_months()
    closed_years = uow.closures.closed_years()
    latest = latest_closure(closed_months, closed_years)
    if latest is None:
        raise ValidationError("Es gibt keinen Abschluss, der wiedereröffnet werden könnte.")
    is_closed = (
        target.year in closed_years
        if target.kind is ClosureKind.YEAR
        else (target.year, target.month) in closed_months
    )
    if not is_closed:
        raise ValidationError(f"{target.label} ist nicht abgeschlossen.")
    if latest != target:
        raise ValidationError(
            "Abschlüsse können nur in umgekehrter Reihenfolge wiedereröffnet werden. "
            f"Zuerst muss {latest.label} wiedereröffnet werden."
        )


def _reopen_audit(
    name: str, target: ClosureRef, signature: str, reason: str, actor_id: str
) -> AuditEntry:
    return AuditEntry(
        name=name,
        entity="period_closures" if target.kind is ClosureKind.MONTH else "year_closures",
        entity_id=None,
        user_id=actor_id,
        old_value=f"{target.label} {signature[:16]}",
        new_value=reason,
    )


def _month_blocker(uow: UnitOfWork, period: tuple[int, int]) -> str | None:
    year, month = period
    if year in uow.closures.closed_years():
        return f"Das Jahr {year} ist bereits abgeschlossen."
    if period in uow.closures.closed_months():
        return f"Der Monat {month:02d}/{year} ist bereits abgeschlossen."
    closed = uow.closures.list_months()
    if closed:
        last = max((c.year, c.month) for c in closed)
        expected = next_period(*last)
        if period != expected:
            return (
                "Die Monate müssen lückenlos nacheinander abgeschlossen werden. "
                f"Nächster abzuschließender Monat ist {expected[1]:02d}/{expected[0]}. "
                "Bitte den Buchungsmonat in der Buchungssteuerung entsprechend setzen."
            )
    return None


def _year_blocker(year: int, closures: dict[int, PeriodClosure], year_closed: bool) -> str | None:
    if year_closed:
        return f"Das Jahr {year} ist bereits abgeschlossen."
    missing = [month for month in range(1, MONTHS_PER_YEAR + 1) if month not in closures]
    if missing:
        names = ", ".join(f"{month:02d}" for month in missing)
        return (
            "Das Jahr kann erst abgeschlossen werden, wenn alle Monate abgeschlossen sind. "
            f"Offen: {names}."
        )
    return None


def _signature_of_month(uow: UnitOfWork, year: int, month: int) -> str:
    return month_signature(
        year,
        month,
        uow.bookings.list_filtered(year, month),
        uow.plans.monthly_plans_for_month(year, month),
    )


def _consistency_problems(uow: UnitOfWork, year: int, month: int) -> list[str]:
    """Prüft vor dem Abschluss, ob Fortschreibung und Buchungen übereinstimmen."""
    labels = {c.id: f"{c.number} {c.name}" for c in uow.cost_centers.list_all()}
    problems: list[str] = []

    booked = {
        cost_center_id: sums
        for (
            cost_center_id,
            booked_year,
            booked_month,
        ), sums in uow.bookings.cost_center_actual_totals().items()
        if (booked_year, booked_month) == (year, month)
    }
    projected = {
        actual.cost_center_id: (actual.debit_cents, actual.credit_cents)
        for actual in uow.plans.list_actuals()
        if (actual.year, actual.month) == (year, month)
    }
    for cost_center_id in projection_mismatches(booked, projected):
        problems.append(
            f"Kostenstelle {labels.get(cost_center_id, cost_center_id)}: Die Ist-Fortschreibung "
            "stimmt nicht mit den Buchungen überein (Projektionen neu aufbauen)."
        )

    transfers = {
        cost_center_id: total
        for (cost_center_id, transfer_year), total in uow.bookings.budget_transfer_totals().items()
        if transfer_year == year
    }
    for plan in uow.plans.list_plans():
        if plan.year == year and plan.budget_transfer_cents != transfers.get(
            plan.cost_center_id, 0
        ):
            problems.append(
                f"Kostenstelle {labels.get(plan.cost_center_id, plan.cost_center_id)}: "
                "Die Ansatzumbuchungen stimmen nicht mit den Buchungen überein."
            )
    if sum(transfers.values()) != 0:
        problems.append(
            "Die Ansatzumbuchungen des Jahres ergeben nicht 0,00 € "
            f"(Differenz {format_euro(sum(transfers.values()))})."
        )
    return problems
