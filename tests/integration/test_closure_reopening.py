from datetime import date

import pytest
from sqlalchemy import select

from conftest import TODAY, World
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.application.services.planning_service import MonthPlanInput, PlanningService
from meine_kasse.domain.enums import BookingType, ClosureKind, ObjectKind, Side
from meine_kasse.domain.errors import PeriodError, ValidationError
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.infrastructure.database.models import (
    AuditLogModel,
    BookingModel,
    ClosureReopeningModel,
)
from meine_kasse.infrastructure.database.session import Database

YEAR = 2026
REASON = "Fehlbuchung wurde entdeckt"


def start_in(control: BookingControlService, month: int, year: int = YEAR) -> None:
    control.update(planning_enabled=False, current_year=year, current_month=month)


def spend(bookings: BookingService, world: World, day: date, cents: int = 5000) -> str:
    return bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=Side.DEBIT,
        amount_cents=cents,
        booking_date=day,
        origin_date=day,
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        actor_id=world.actor,
    )


def close_months(closing: ClosingService, world: World, count: int) -> None:
    for _ in range(count):
        closing.close_month(actor_id=world.actor)


def audit(database: Database, name: str) -> list[AuditLogModel]:
    with database.session_factory() as session:
        return list(session.scalars(select(AuditLogModel).where(AuditLogModel.name == name)))


def test_reopening_the_last_month_makes_it_editable_again_and_rewinds_the_booking_month(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
    database: Database,
) -> None:
    start_in(booking_control, 5)
    booking_id = spend(bookings, world, date(2026, 5, 10))
    result = closing.close_month(actor_id=world.actor)
    with pytest.raises(PeriodError):
        bookings.delete(booking_id, actor_id=world.actor)

    closing.reopen_month(2026, 5, reason=REASON, actor_id=world.actor)

    control = booking_control.get()
    assert (control.current_year, control.current_month) == (2026, 5)
    assert (control.last_closed_year, control.last_closed_month) == (None, None)
    overview = closing.get_overview(YEAR)
    assert overview.months[4].is_closed is False and overview.months[4].is_current
    bookings.delete(booking_id, actor_id=world.actor)
    spend(bookings, world, date(2026, 5, 12))

    (entry,) = closing.list_reopenings()
    assert entry.ref.kind is ClosureKind.MONTH and entry.ref.label == "Monat 05/2026"
    assert entry.reason == REASON
    assert entry.reopened_on == TODAY
    assert entry.reopened_by == "A A"
    assert entry.previous_closed_by == "A A"
    assert entry.previous_closed_on == TODAY
    assert entry.signature_was_valid is True
    with database.session_factory() as session:
        stored = session.scalars(select(ClosureReopeningModel)).one()
        assert stored.previous_signature == result.signature
    (audit_entry,) = audit(database, "MONTH_REOPENED")
    assert REASON in (audit_entry.new_value or "")
    assert result.signature[:16] in (audit_entry.old_value or "")


def test_reason_is_mandatory_and_a_rejected_attempt_changes_nothing(
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    start_in(booking_control, 5)
    closing.close_month(actor_id=world.actor)

    for reason in ("", "kurz"):
        with pytest.raises(ValidationError, match="Begründung"):
            closing.reopen_month(2026, 5, reason=reason, actor_id=world.actor)

    assert closing.get_overview(YEAR).months[4].is_closed is True
    assert closing.list_reopenings() == []


def test_months_can_only_be_reopened_in_reverse_order(
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    start_in(booking_control, 1)
    close_months(closing, world, 3)
    assert closing.get_overview(YEAR).reopen_target is not None
    assert closing.get_overview(YEAR).reopen_target.label == "Monat 03/2026"  # type: ignore[union-attr]

    with pytest.raises(ValidationError, match="umgekehrter Reihenfolge") as error:
        closing.reopen_month(2026, 2, reason=REASON, actor_id=world.actor)
    assert "Monat 03/2026" in str(error.value)
    with pytest.raises(ValidationError, match="Monat 03/2026"):
        closing.reopen_month(2026, 1, reason=REASON, actor_id=world.actor)

    closing.reopen_month(2026, 3, reason=REASON, actor_id=world.actor)
    control = booking_control.get()
    assert (control.last_closed_month, control.current_month) == (2, 3)
    closing.reopen_month(2026, 2, reason=REASON, actor_id=world.actor)
    closing.reopen_month(2026, 1, reason=REASON, actor_id=world.actor)

    control = booking_control.get()
    assert control.last_closed_month is None and control.current_month == 1
    assert closing.get_overview(YEAR).reopen_target is None
    assert [item.ref.label for item in closing.list_reopenings()] == [
        "Monat 01/2026",
        "Monat 02/2026",
        "Monat 03/2026",
    ]


def test_reopening_something_not_closed_is_refused(
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    with pytest.raises(ValidationError, match="keinen Abschluss"):
        closing.reopen_month(2026, 5, reason=REASON, actor_id=world.actor)
    start_in(booking_control, 5)
    closing.close_month(actor_id=world.actor)
    with pytest.raises(ValidationError, match="nicht abgeschlossen"):
        closing.reopen_month(2026, 7, reason=REASON, actor_id=world.actor)
    with pytest.raises(ValidationError, match="nicht abgeschlossen"):
        closing.reopen_year(2026, reason=REASON, actor_id=world.actor)


def test_manipulated_data_is_documented_as_invalid_signature(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    database: Database,
    world: World,
) -> None:
    start_in(booking_control, 5)
    booking_id = spend(bookings, world, date(2026, 5, 10))
    closing.close_month(actor_id=world.actor)
    with database.session_factory() as session:
        session.get(BookingModel, booking_id).amount_cents = 1  # type: ignore[union-attr]
        session.commit()

    closing.reopen_month(2026, 5, reason=REASON, actor_id=world.actor)

    (entry,) = closing.list_reopenings()
    assert entry.signature_was_valid is False


def test_year_closing_must_be_reopened_before_its_months(
    closing: ClosingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    start_in(booking_control, 1)
    close_months(closing, world, 12)
    closing.close_year(YEAR, actor_id=world.actor)
    assert closing.get_overview(YEAR).reopen_target.label == "Jahr 2026"  # type: ignore[union-attr]

    with pytest.raises(ValidationError, match="Jahr 2026"):
        closing.reopen_month(2026, 12, reason=REASON, actor_id=world.actor)

    closing.reopen_year(YEAR, reason=REASON, actor_id=world.actor)

    assert closing.get_overview(YEAR).year_closed is False
    assert closing.get_overview(YEAR).reopen_target.label == "Monat 12/2026"  # type: ignore[union-attr]
    (entry,) = closing.list_reopenings()
    assert entry.ref.kind is ClosureKind.YEAR and entry.ref.month is None
    assert entry.signature_was_valid is True
    assert len(audit(database, "YEAR_REOPENED")) == 1

    closing.reopen_month(2026, 12, reason=REASON, actor_id=world.actor)
    control = booking_control.get()
    assert (control.current_year, control.current_month) == (2026, 12)
    assert (control.last_closed_year, control.last_closed_month) == (2026, 11)


def test_a_year_cannot_be_reopened_while_a_later_month_is_closed(
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    start_in(booking_control, 1)
    close_months(closing, world, 12)
    closing.close_year(YEAR, actor_id=world.actor)
    closing.close_month(actor_id=world.actor)  # Januar 2027

    with pytest.raises(ValidationError, match="Monat 01/2027"):
        closing.reopen_year(YEAR, reason=REASON, actor_id=world.actor)

    closing.reopen_month(2027, 1, reason=REASON, actor_id=world.actor)
    closing.reopen_year(YEAR, reason=REASON, actor_id=world.actor)
    assert [item.ref.label for item in closing.list_reopenings()] == ["Jahr 2026", "Monat 01/2027"]


def test_reopened_year_can_be_closed_again_with_a_new_signature_after_a_correction(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    start_in(booking_control, 1)
    booking_id = spend(bookings, world, date(2026, 1, 10))
    close_months(closing, world, 12)
    first_year_signature = closing.close_year(YEAR, actor_id=world.actor)

    closing.reopen_year(YEAR, reason=REASON, actor_id=world.actor)
    for month in range(12, 0, -1):
        closing.reopen_month(2026, month, reason=REASON, actor_id=world.actor)
    bookings.delete(booking_id, actor_id=world.actor)
    close_months(closing, world, 12)
    second_year_signature = closing.close_year(YEAR, actor_id=world.actor)

    assert second_year_signature != first_year_signature
    assert len(closing.list_reopenings()) == 13
    assert all(check.ok for check in closing.verify_closures())


def test_reopened_month_allows_planning_changes_again(
    closing: ClosingService,
    booking_control: BookingControlService,
    planning: PlanningService,
    world: World,
) -> None:
    start_in(booking_control, 5)
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=10000,
        months=[MonthPlanInput(5, 1000)],
        actor_id=world.actor,
    )
    closing.close_month(actor_id=world.actor)
    with pytest.raises(PeriodError):
        planning.save_plan(
            world.cc_a,
            YEAR,
            base_budget_cents=10000,
            months=[MonthPlanInput(5, 2000)],
            actor_id=world.actor,
        )

    closing.reopen_month(2026, 5, reason=REASON, actor_id=world.actor)
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=10000,
        months=[MonthPlanInput(5, 2000)],
        actor_id=world.actor,
    )
    assert planning.get_plan_view(world.cc_a, YEAR).months[4].plan_cents == 2000


def test_reopening_history_survives_reclosing(
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    start_in(booking_control, 5)
    closing.close_month(actor_id=world.actor)
    closing.reopen_month(2026, 5, reason=REASON, actor_id=world.actor)
    closing.close_month(actor_id=world.actor)

    assert closing.get_overview(YEAR).months[4].is_closed is True
    assert len(closing.list_reopenings()) == 1
