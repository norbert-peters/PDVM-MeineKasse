from datetime import date

import pytest
from sqlalchemy import select

from conftest import TODAY, World
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.application.services.planning_service import MonthPlanInput, PlanningService
from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import PeriodError, ValidationError
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.infrastructure.database.models import (
    AuditLogModel,
    BookingControlModel,
    BookingModel,
    MonthlyActualModel,
    MonthlyPlanModel,
)
from meine_kasse.infrastructure.database.session import Database

YEAR = 2026


def start_in(booking_control: BookingControlService, month: int, year: int = YEAR) -> None:
    booking_control.update(planning_enabled=False, current_year=year, current_month=month)


def spend(
    bookings: BookingService,
    world: World,
    *,
    day: date,
    cents: int = 5000,
    side: Side = Side.DEBIT,
    text: str = "Einkauf",
) -> str:
    return bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=side,
        amount_cents=cents,
        booking_date=day,
        origin_date=day,
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        booking_text=text,
        actor_id=world.actor,
    )


def audit_names(database: Database) -> list[str]:
    with database.session_factory() as session:
        return [row.name for row in session.scalars(select(AuditLogModel))]


def test_closing_a_month_signs_it_and_advances_the_booking_month(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    database: Database,
    world: World,
) -> None:
    start_in(booking_control, 5)
    spend(bookings, world, day=date(2026, 5, 10))

    result = closing.close_month(actor_id=world.actor)

    assert (result.year, result.month) == (2026, 5)
    assert (result.next_year, result.next_month) == (2026, 6)
    assert len(result.signature) == 64
    control = booking_control.get()
    assert (control.current_year, control.current_month) == (2026, 6)
    assert (control.last_closed_year, control.last_closed_month) == (2026, 5)
    assert "MONTH_CLOSED" in audit_names(database)
    overview = closing.get_overview(YEAR)
    may = overview.months[4]
    assert may.is_closed and may.closed_on == TODAY and may.signature == result.signature
    assert overview.months[5].is_current and not overview.months[5].is_closed


def test_closed_month_locks_bookings_planning_and_changes(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
) -> None:
    start_in(booking_control, 5)
    booking_id = spend(bookings, world, day=date(2026, 5, 10))
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=10000,
        months=[MonthPlanInput(5, 1000)],
        actor_id=world.actor,
    )
    closing.close_month(actor_id=world.actor)

    with pytest.raises(PeriodError, match="05/2026"):
        spend(bookings, world, day=date(2026, 5, 20))
    with pytest.raises(PeriodError, match="Storno"):
        bookings.delete(booking_id, actor_id=world.actor)
    with pytest.raises(PeriodError):
        planning.save_plan(
            world.cc_a,
            YEAR,
            base_budget_cents=10000,
            months=[MonthPlanInput(5, 2000)],
            actor_id=world.actor,
        )
    # Korrektur per Storno im offenen Monat
    reversal = bookings.reverse(booking_id, booking_date=date(2026, 6, 2), actor_id=world.actor)
    assert bookings.get_booking(reversal).amount_cents == -5000


def test_months_must_be_closed_without_gaps(
    closing: ClosingService, booking_control: BookingControlService, world: World
) -> None:
    start_in(booking_control, 1)
    closing.close_month(actor_id=world.actor)
    booking_control.update(planning_enabled=False, current_year=YEAR, current_month=3)

    overview = closing.get_overview(YEAR)
    assert overview.can_close_month is False
    assert "02/2026" in (overview.month_blocker or "")
    with pytest.raises(ValidationError, match="lückenlos"):
        closing.close_month(actor_id=world.actor)

    start_in(booking_control, 2)
    closing.close_month(actor_id=world.actor)
    assert closing.get_overview(YEAR).can_close_month is True


def test_inconsistent_projection_blocks_closing_until_rebuilt(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    database: Database,
    world: World,
) -> None:
    start_in(booking_control, 5)
    spend(bookings, world, day=date(2026, 5, 10), cents=5000)
    with database.session_factory() as session:
        actual = session.scalars(select(MonthlyActualModel)).one()
        actual.debit_cents = 4999
        session.commit()

    with pytest.raises(ValidationError, match="Ist-Fortschreibung") as error:
        closing.close_month(actor_id=world.actor)
    assert "100 Lebensmittel" in str(error.value)
    assert booking_control.get().current_month == 5

    bookings.rebuild_projections(actor_id=world.actor)
    closing.close_month(actor_id=world.actor)


def test_inconsistent_budget_transfers_block_closing(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    database: Database,
    world: World,
) -> None:
    planning.save_plan(world.cc_a, YEAR, base_budget_cents=10000, months=[], actor_id=world.actor)
    planning.save_plan(world.cc_b, YEAR, base_budget_cents=0, months=[], actor_id=world.actor)
    booking_control.update(planning_enabled=True, current_year=YEAR, current_month=5)
    bookings.post(
        booking_type=BookingType.BUDGET_TRANSFER,
        entry_side=Side.DEBIT,
        amount_cents=3000,
        booking_date=date(2026, 5, 5),
        origin_date=date(2026, 5, 5),
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.COST_CENTER, world.cc_b),
        actor_id=world.actor,
    )
    from meine_kasse.infrastructure.database.models import CostCenterPlanModel

    with database.session_factory() as session:
        plan = session.scalars(
            select(CostCenterPlanModel).where(CostCenterPlanModel.cost_center_id == world.cc_b)
        ).one()
        plan.budget_transfer_cents = 2000
        session.commit()

    with pytest.raises(ValidationError, match="Ansatzumbuchungen"):
        closing.close_month(actor_id=world.actor)
    bookings.rebuild_projections(actor_id=world.actor)
    closing.close_month(actor_id=world.actor)


def test_verification_detects_later_manipulation(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    database: Database,
    world: World,
) -> None:
    start_in(booking_control, 5)
    booking_id = spend(bookings, world, day=date(2026, 5, 10))
    closing.close_month(actor_id=world.actor)
    assert [check.ok for check in closing.verify_closures()] == [True]

    with database.session_factory() as session:
        session.get(BookingModel, booking_id).amount_cents = 1  # type: ignore[union-attr]
        session.commit()

    (check,) = closing.verify_closures()
    assert check.ok is False
    assert check.month == 5 and "ABWEICHEND" in check.message


def test_verification_detects_changed_plan_values(
    closing: ClosingService,
    booking_control: BookingControlService,
    planning: PlanningService,
    database: Database,
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
    with database.session_factory() as session:
        session.scalars(
            select(MonthlyPlanModel).where(MonthlyPlanModel.month == 5)
        ).one().plan_cents = 2000
        session.commit()
    assert [check.ok for check in closing.verify_closures()] == [False]


def close_all_months(closing: ClosingService, world: World) -> None:
    for _ in range(12):
        closing.close_month(actor_id=world.actor)


def test_year_closing_requires_all_months_and_locks_the_year(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    database: Database,
    world: World,
) -> None:
    start_in(booking_control, 1)
    spend(bookings, world, day=date(2026, 1, 10))
    for _ in range(11):
        closing.close_month(actor_id=world.actor)

    overview = closing.get_overview(YEAR)
    assert overview.can_close_year is False
    assert "12" in (overview.year_blocker or "")
    with pytest.raises(ValidationError, match="alle Monate"):
        closing.close_year(YEAR, actor_id=world.actor)

    closing.close_month(actor_id=world.actor)
    control = booking_control.get()
    assert (control.current_year, control.current_month) == (2027, 1)
    assert closing.get_overview(YEAR).can_close_year is True

    signature = closing.close_year(YEAR, actor_id=world.actor)

    assert len(signature) == 64
    overview = closing.get_overview(YEAR)
    assert overview.year_closed and overview.year_signature == signature
    assert overview.can_close_year is False
    assert "YEAR_CLOSED" in audit_names(database)
    with pytest.raises(PeriodError, match="2026"):
        spend(bookings, world, day=date(2026, 12, 31))
    with pytest.raises(PeriodError):
        planning.save_plan(world.cc_a, YEAR, base_budget_cents=0, months=[], actor_id=world.actor)
    with pytest.raises(ValidationError, match="bereits abgeschlossen"):
        closing.close_year(YEAR, actor_id=world.actor)
    checks = closing.verify_closures()
    assert len(checks) == 13 and all(check.ok for check in checks)
    spend(bookings, world, day=date(2027, 1, 15))


def test_year_closing_is_refused_when_a_month_signature_no_longer_matches(
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    database: Database,
    world: World,
) -> None:
    start_in(booking_control, 1)
    booking_id = spend(bookings, world, day=date(2026, 2, 10))
    close_all_months(closing, world)
    with database.session_factory() as session:
        session.get(BookingModel, booking_id).amount_cents = 7  # type: ignore[union-attr]
        session.commit()

    with pytest.raises(ValidationError, match="02/2026"):
        closing.close_year(YEAR, actor_id=world.actor)


def test_closing_an_empty_month_is_allowed(
    closing: ClosingService, booking_control: BookingControlService, world: World
) -> None:
    start_in(booking_control, 8)
    result = closing.close_month(actor_id=world.actor)
    assert result.signature


def test_a_closed_month_cannot_be_closed_again_even_if_the_booking_month_is_reset(
    closing: ClosingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    start_in(booking_control, 5)
    closing.close_month(actor_id=world.actor)
    with database.session_factory() as session:
        control = session.scalars(select(BookingControlModel)).one()
        control.current_month, control.last_closed_month = 5, None
        session.commit()

    assert "bereits abgeschlossen" in (closing.get_overview(YEAR).month_blocker or "")
    with pytest.raises(ValidationError, match="bereits abgeschlossen"):
        closing.close_month(actor_id=world.actor)
