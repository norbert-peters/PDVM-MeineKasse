"""Plan-Ist nach Entstehungsdatum (Architekturvorgabe 2.11)."""

from datetime import date

import pytest
from sqlalchemy import select

from conftest import World
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import BudgetExceededError, PeriodError, PlanPeriodError
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.infrastructure.database.migrate import downgrade_database, upgrade_database
from meine_kasse.infrastructure.database.models import (
    BookingModel,
    CostCenterPlanModel,
    MonthlyActualModel,
    PeriodClosureModel,
    YearClosureModel,
)
from meine_kasse.infrastructure.database.session import Database

BOOKED = date(2026, 5, 10)


def _post(
    bookings: BookingService,
    world: World,
    *,
    origin: date,
    booked: date = BOOKED,
    amount: int = 5000,
    cost_center: str | None = None,
    side: Side = Side.DEBIT,
) -> str:
    return bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=side,
        amount_cents=amount,
        booking_date=booked,
        origin_date=origin,
        leading=Stelle(ObjectKind.COST_CENTER, cost_center or world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        booking_text="Test",
        actor_id=world.actor,
    )


def _actuals(database: Database) -> dict[tuple[str, int, int], tuple[int, int]]:
    with database.session_factory() as session:
        return {
            (row.cost_center_id, row.year, row.month): (row.debit_cents, row.credit_cents)
            for row in session.scalars(select(MonthlyActualModel))
            if row.debit_cents or row.credit_cents
        }


def _plan(database: Database, cost_center_id: str, year: int, base_cents: int = 0) -> None:
    with database.session_factory() as session:
        session.add(
            CostCenterPlanModel(
                cost_center_id=cost_center_id, year=year, base_budget_cents=base_cents
            )
        )
        session.commit()


def _close_month(database: Database, world: World, year: int, month: int) -> None:
    with database.session_factory() as session:
        session.add(
            PeriodClosureModel(
                year=year,
                month=month,
                closed_on=date(year, month, 28),
                closed_by_user_id=world.actor,
                signature="x" * 64,
            )
        )
        session.commit()


def _close_year(database: Database, world: World, year: int) -> None:
    with database.session_factory() as session:
        session.add(
            YearClosureModel(
                year=year,
                closed_on=date(year, 12, 31),
                closed_by_user_id=world.actor,
                signature="y" * 64,
            )
        )
        session.commit()


def _enable_planning(booking_control: BookingControlService) -> None:
    booking_control.update(planning_enabled=True, current_year=2026, current_month=5)


# Zuordnung zum Planmonat


def test_actual_goes_to_the_month_of_the_origin_date_not_the_booking_date(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = _post(bookings, world, origin=date(2026, 3, 20))

    booking = bookings.get_booking(booking_id)
    assert (booking.fiscal_year, booking.fiscal_month) == (2026, 5)
    assert _actuals(database) == {(world.cc_a, 2026, 3): (5000, 0)}
    assert bookings.account_balance(world.giro) == -5000


def test_closed_plan_month_in_an_open_year_can_still_be_booked(
    bookings: BookingService, database: Database, world: World
) -> None:
    _close_month(database, world, 2026, 3)

    _post(bookings, world, origin=date(2026, 3, 20))

    assert _actuals(database) == {(world.cc_a, 2026, 3): (5000, 0)}


def test_reversal_balances_in_the_same_plan_month(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = _post(bookings, world, origin=date(2026, 3, 20))

    reversal_id = bookings.reverse(booking_id, booking_date=date(2026, 5, 12), actor_id=world.actor)

    assert bookings.get_booking(reversal_id).origin_date == date(2026, 3, 20)
    assert _actuals(database) == {}


def test_update_moves_the_effect_between_plan_months(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = _post(bookings, world, origin=date(2026, 3, 20))
    current = bookings.get_booking(booking_id)

    bookings.update(
        booking_id,
        booking_type=current.booking_type,
        entry_side=current.entry_side,
        amount_cents=current.amount_cents,
        booking_date=current.booking_date,
        origin_date=date(2026, 4, 2),
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        actor_id=world.actor,
    )

    assert _actuals(database) == {(world.cc_a, 2026, 4): (5000, 0)}


def test_month_closing_works_with_a_different_plan_month(
    bookings: BookingService, closing: ClosingService, database: Database, world: World
) -> None:
    _post(bookings, world, origin=date(2026, 3, 20))

    closing.close_month(actor_id=world.actor)

    assert all(check.ok for check in closing.verify_closures())


def test_rebuild_reproduces_the_projection_by_origin_date(
    bookings: BookingService, database: Database, world: World
) -> None:
    _post(bookings, world, origin=date(2026, 3, 20))
    _post(bookings, world, origin=date(2026, 5, 2), amount=700)
    _post(bookings, world, origin=date(2026, 3, 21), amount=300, side=Side.CREDIT)
    before = _actuals(database)

    bookings.rebuild_projections()

    assert _actuals(database) == before
    assert before[(world.cc_a, 2026, 3)] == (5000, 300)


# Planjahr


def test_other_year_without_plan_is_not_booked(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    _enable_planning(booking_control)

    with pytest.raises(PlanPeriodError, match="kein Plan"):
        _post(bookings, world, origin=date(2025, 12, 20))

    assert _actuals(database) == {}
    with database.session_factory() as session:
        assert session.scalars(select(BookingModel)).first() is None


def test_previous_year_with_open_plan_is_booked_there_and_checked_against_its_budget(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    _enable_planning(booking_control)
    _plan(database, world.cc_a, 2025, base_cents=10000)

    _post(bookings, world, origin=date(2025, 12, 20), amount=6000)

    assert _actuals(database) == {(world.cc_a, 2025, 12): (6000, 0)}
    with pytest.raises(BudgetExceededError):
        _post(bookings, world, origin=date(2025, 12, 21), amount=5000)


def test_closed_plan_year_is_never_booked_even_with_a_plan(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    _enable_planning(booking_control)
    _plan(database, world.cc_a, 2025, base_cents=10000)
    _close_year(database, world, 2025)

    with pytest.raises(PlanPeriodError, match="abgeschlossen"):
        _post(bookings, world, origin=date(2025, 12, 20))

    assert _actuals(database) == {}


def test_closed_plan_year_is_rejected_without_active_planning(
    bookings: BookingService, database: Database, world: World
) -> None:
    _close_year(database, world, 2025)

    with pytest.raises(PlanPeriodError):
        _post(bookings, world, origin=date(2025, 12, 20))


def test_plan_error_is_a_period_error(
    bookings: BookingService, database: Database, world: World
) -> None:
    _close_year(database, world, 2025)

    with pytest.raises(PeriodError):
        _post(bookings, world, origin=date(2025, 12, 20))


def test_other_year_without_plan_is_allowed_when_planning_is_inactive_or_not_planned(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    _post(bookings, world, origin=date(2025, 12, 20))
    _enable_planning(booking_control)

    _post(bookings, world, origin=date(2025, 12, 21), cost_center=world.cc_free)

    assert (world.cc_free, 2025, 12) in _actuals(database)


def test_next_year_needs_a_plan_too(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    _enable_planning(booking_control)

    with pytest.raises(PlanPeriodError):
        _post(bookings, world, origin=date(2027, 1, 5))


# Korrektur bei abgeschlossenem Planjahr


def _booking_with_closed_plan_year(
    bookings: BookingService, database: Database, world: World
) -> str:
    _plan(database, world.cc_a, 2025, base_cents=10000)
    booking_id = _post(bookings, world, origin=date(2025, 12, 20), amount=6000)
    _close_year(database, world, 2025)
    return booking_id


def test_booking_in_a_closed_plan_year_can_only_be_reversed(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = _booking_with_closed_plan_year(bookings, database, world)
    view = next(v for v in bookings.list_bookings(year=2026) if v.id == booking_id)

    assert view.is_plan_year_closed
    assert not view.can_edit and not view.can_delete and view.can_reverse
    with pytest.raises(PlanPeriodError, match="Gegenbuchung"):
        bookings.delete(booking_id, actor_id=world.actor)


def test_reversal_of_a_closed_plan_year_acts_in_its_own_year(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = _booking_with_closed_plan_year(bookings, database, world)

    reversal_id = bookings.reverse(booking_id, booking_date=date(2026, 5, 12), actor_id=world.actor)

    assert bookings.get_booking(reversal_id).origin_date == date(2026, 5, 12)
    assert _actuals(database) == {
        (world.cc_a, 2025, 12): (6000, 0),
        (world.cc_a, 2026, 5): (-6000, 0),
    }
    assert bookings.account_balance(world.giro) == 0


# Anzeige im Buchungsdialog


def test_cost_center_info_uses_the_plan_period_and_reports_unusable_years(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    _enable_planning(booking_control)
    _plan(database, world.cc_a, 2025, base_cents=10000)
    _post(bookings, world, origin=date(2025, 12, 20), amount=4000)

    info = bookings.cost_center_info(world.cc_a, date(2025, 12, 1))
    assert (info.year, info.annual_budget_cents, info.remaining_cents) == (2025, 10000, 6000)
    assert info.month_movement_cents == 4000

    with pytest.raises(PlanPeriodError):
        bookings.cost_center_info(world.cc_b, date(2025, 12, 1))


# Migration


def test_migration_rebuilds_projection_by_origin_date(
    bookings: BookingService, database: Database, world: World
) -> None:
    _post(bookings, world, origin=date(2026, 3, 20))
    _post(bookings, world, origin=date(2026, 5, 2), amount=700)
    expected = _actuals(database)
    with database.session_factory() as session:
        rows = list(session.scalars(select(MonthlyActualModel)))
        for row in rows:
            if row.month == 3:
                session.delete(row)  # fehlende Zeile, wird neu angelegt
            else:
                row.debit_cents = 999  # veralteter Stand nach Buchungsmonat
        session.commit()

    downgrade_database(database.engine, "0004")
    upgrade_database(database.engine)

    assert _actuals(database) == expected
