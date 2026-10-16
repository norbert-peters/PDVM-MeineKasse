from datetime import date

import pytest
from sqlalchemy import func, select

from conftest import World
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import (
    BudgetExceededError,
    NotFoundError,
    PeriodError,
    ValidationError,
)
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.infrastructure.database.models import (
    AuditLogModel,
    BookingModel,
    CostCenterPlanModel,
    MonthlyActualModel,
    MonthlyPlanModel,
    PeriodClosureModel,
)
from meine_kasse.infrastructure.database.repositories import SqlPlanRepository
from meine_kasse.infrastructure.database.session import Database

D = date(2026, 5, 10)
YEAR = 2026


def cc(entity_id: str) -> Stelle:
    return Stelle(ObjectKind.COST_CENTER, entity_id)


def acc(entity_id: str) -> Stelle:
    return Stelle(ObjectKind.ACCOUNT, entity_id)


def book(
    bookings: BookingService,
    world: World,
    *,
    side: Side = Side.DEBIT,
    amount: int = 5000,
    cost_center: str | None = None,
    account: str | None = None,
    booking_date: date = D,
    text: str = "Einkauf",
) -> str:
    return bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=side,
        amount_cents=amount,
        booking_date=booking_date,
        origin_date=booking_date,
        leading=cc(cost_center or world.cc_a),
        second=acc(account or world.giro),
        merchant="Markt",
        booking_text=text,
        actor_id=world.actor,
    )


def transfer(
    bookings: BookingService,
    world: World,
    *,
    leading: str,
    second: str,
    side: Side = Side.DEBIT,
    amount: int = 1000,
) -> str:
    return bookings.post(
        booking_type=BookingType.BUDGET_TRANSFER,
        entry_side=side,
        amount_cents=amount,
        booking_date=D,
        origin_date=D,
        leading=cc(leading),
        second=cc(second),
        booking_text="Ansatz",
        actor_id=world.actor,
    )


def set_budget(database: Database, cost_center_id: str, base_cents: int) -> None:
    with database.session_factory() as session:
        session.add(
            CostCenterPlanModel(
                cost_center_id=cost_center_id, year=YEAR, base_budget_cents=base_cents
            )
        )
        session.commit()


def enable_planning(booking_control: BookingControlService, enabled: bool = True) -> None:
    booking_control.update(planning_enabled=enabled, current_year=YEAR, current_month=5)


def actuals(database: Database) -> dict[tuple[str, int], tuple[int, int]]:
    """(Kostenstelle, Monat) -> (Soll, Haben) ohne Nullzeilen."""
    with database.session_factory() as session:
        rows = session.scalars(select(MonthlyActualModel)).all()
        return {
            (row.cost_center_id, row.month): (row.debit_cents, row.credit_cents)
            for row in rows
            if row.debit_cents or row.credit_cents
        }


def booking_count(database: Database) -> int:
    with database.session_factory() as session:
        return session.scalar(select(func.count()).select_from(BookingModel)) or 0


def audit_names(database: Database) -> list[str]:
    with database.session_factory() as session:
        return [row.name for row in session.scalars(select(AuditLogModel))]


# Ist-Buchungen


def test_actual_booking_is_aligned_and_updates_projection(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = book(bookings, world, side=Side.DEBIT, amount=5000)

    booking = bookings.get_booking(booking_id)
    assert [leg.side for leg in booking.legs] == [Side.DEBIT, Side.DEBIT]
    assert booking.legs[0].cost_center_id == world.cc_a
    assert booking.legs[1].account_id == world.giro
    assert (booking.fiscal_year, booking.fiscal_month) == (2026, 5)
    assert actuals(database) == {(world.cc_a, 5): (5000, 0)}
    assert bookings.account_balance(world.giro) == -5000
    assert "BOOKING_CREATED" in audit_names(database)


def test_negative_debit_stays_a_negative_debit(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = book(bookings, world, side=Side.DEBIT, amount=-5000)

    booking = bookings.get_booking(booking_id)
    assert booking.amount_cents == -5000
    assert booking.entry_side is Side.DEBIT
    assert actuals(database) == {(world.cc_a, 5): (-5000, 0)}
    assert bookings.account_balance(world.giro) == 5000


def test_credit_booking_increases_balance(
    bookings: BookingService, database: Database, world: World
) -> None:
    book(bookings, world, side=Side.CREDIT, amount=2000)
    assert actuals(database) == {(world.cc_a, 5): (0, 2000)}
    assert bookings.account_balance(world.giro) == 2000


def test_zero_amount_is_rejected(bookings: BookingService, world: World) -> None:
    with pytest.raises(ValidationError, match="0"):
        book(bookings, world, amount=0)


def test_wrong_stellen_for_booking_type_are_rejected(
    bookings: BookingService, world: World
) -> None:
    with pytest.raises(ValidationError):
        bookings.post(
            booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
            entry_side=Side.DEBIT,
            amount_cents=100,
            booking_date=D,
            origin_date=D,
            leading=acc(world.giro),
            second=cc(world.cc_a),
            actor_id=world.actor,
        )


def test_unknown_and_inactive_stellen_are_rejected(
    bookings: BookingService, master_data: MasterDataService, world: World
) -> None:
    with pytest.raises(NotFoundError):
        book(bookings, world, cost_center="unbekannt")
    master_data.set_account_active(world.giro, False)
    with pytest.raises(ValidationError, match="inaktiv"):
        book(bookings, world)


# Zeitraum


@pytest.mark.parametrize("booking_date", [date(2026, 3, 31), date(2026, 7, 1)])
def test_booking_outside_window_is_rejected(
    bookings: BookingService, database: Database, world: World, booking_date: date
) -> None:
    with pytest.raises(PeriodError, match="außerhalb"):
        book(bookings, world, booking_date=booking_date)
    assert booking_count(database) == 0


@pytest.mark.parametrize("booking_date", [date(2026, 4, 1), date(2026, 6, 30)])
def test_booking_at_window_edges_is_allowed(
    bookings: BookingService, world: World, booking_date: date
) -> None:
    book(bookings, world, booking_date=booking_date)


def test_booking_in_closed_month_is_rejected(
    bookings: BookingService, database: Database, world: World
) -> None:
    _close_month(database, world.actor, 2026, 4)
    with pytest.raises(PeriodError, match="04/2026"):
        book(bookings, world, booking_date=date(2026, 4, 20))


def _close_month(database: Database, actor: str, year: int, month: int) -> None:
    with database.session_factory() as session:
        session.add(
            PeriodClosureModel(
                year=year,
                month=month,
                closed_on=date(year, month, 28),
                closed_by_user_id=actor,
                signature="x" * 64,
            )
        )
        session.commit()


def test_period_status_marks_free_and_fixed_months(
    bookings: BookingService, database: Database, world: World
) -> None:
    _close_month(database, world.actor, 2026, 4)
    assert bookings.period_status(date(2026, 5, 3)).state.value == "OPEN"
    assert "frei" in bookings.period_status(date(2026, 5, 3)).message
    assert bookings.period_status(date(2026, 4, 3)).state.value == "CLOSED"
    assert "fix" in bookings.period_status(date(2026, 4, 3)).message
    assert bookings.period_status(date(2026, 9, 3)).state.value == "OUTSIDE_WINDOW"


def test_default_booking_date_is_today_inside_window(bookings: BookingService) -> None:
    assert bookings.default_booking_date() == date(2026, 5, 15)


def test_default_booking_date_falls_back_to_first_of_current_month(
    bookings: BookingService, booking_control: BookingControlService
) -> None:
    booking_control.update(planning_enabled=False, current_year=2026, current_month=9)
    assert bookings.default_booking_date() == date(2026, 9, 1)


def test_default_booking_date_skips_a_closed_month(
    bookings: BookingService,
    booking_control: BookingControlService,
    closing: ClosingService,
    world: World,
) -> None:
    closing.close_month(actor_id=world.actor)  # Mai 2026, heute ist der 15.05.

    assert booking_control.get().current_month == 6
    assert bookings.default_booking_date() == date(2026, 6, 1)


# Ansatzsperre


def test_booking_up_to_remaining_budget_is_allowed_and_one_cent_more_is_blocked(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 10000)
    book(bookings, world, amount=10000)
    before = (booking_count(database), actuals(database), audit_names(database))

    with pytest.raises(BudgetExceededError) as error:
        book(bookings, world, amount=1)

    assert error.value.shortfall_cents == 1
    assert (booking_count(database), actuals(database), audit_names(database)) == before


def test_relieving_bookings_are_never_blocked_and_free_budget(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 10000)
    book(bookings, world, amount=10000)

    book(bookings, world, side=Side.CREDIT, amount=500)
    book(bookings, world, side=Side.DEBIT, amount=-500)
    book(bookings, world, amount=1000)
    info = bookings.cost_center_info(world.cc_a, D)
    assert info.remaining_cents == 0


def test_cost_center_without_plan_and_inactive_planning_are_not_checked(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    book(bookings, world, amount=999999)
    enable_planning(booking_control)
    book(bookings, world, cost_center=world.cc_free, amount=999999)
    with pytest.raises(BudgetExceededError):
        book(bookings, world, cost_center=world.cc_b, amount=1)


# Ansatzumbuchung


def test_budget_transfer_moves_budget_without_touching_actuals_or_accounts(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 10000)
    set_budget(database, world.cc_b, 0)

    transfer(bookings, world, leading=world.cc_a, second=world.cc_b, amount=3000)

    assert bookings.cost_center_info(world.cc_a, D).annual_budget_cents == 7000
    assert bookings.cost_center_info(world.cc_b, D).annual_budget_cents == 3000
    assert actuals(database) == {}
    assert bookings.account_balance(world.giro) == 0
    book(bookings, world, cost_center=world.cc_b, amount=3000)
    with pytest.raises(BudgetExceededError):
        book(bookings, world, cost_center=world.cc_b, amount=1)


def test_budget_transfer_in_credit_direction_reverses_the_effect(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 1000)
    set_budget(database, world.cc_b, 5000)

    transfer(bookings, world, leading=world.cc_a, second=world.cc_b, side=Side.CREDIT, amount=2000)

    assert bookings.cost_center_info(world.cc_a, D).annual_budget_cents == 3000
    assert bookings.cost_center_info(world.cc_b, D).annual_budget_cents == 3000


def test_budget_transfer_cannot_give_away_used_or_distributed_budget(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 10000)
    set_budget(database, world.cc_b, 0)
    book(bookings, world, amount=8000)
    with pytest.raises(BudgetExceededError) as error:
        transfer(bookings, world, leading=world.cc_a, second=world.cc_b, amount=2001)
    assert "20,00 €" in str(error.value)
    transfer(bookings, world, leading=world.cc_a, second=world.cc_b, amount=2000)

    with database.session_factory() as session:
        plan = session.scalars(
            select(CostCenterPlanModel).where(CostCenterPlanModel.cost_center_id == world.cc_b)
        ).one()
        session.add(MonthlyPlanModel(cost_center_plan_id=plan.id, month=5, plan_cents=1500))
        session.commit()
    with pytest.raises(BudgetExceededError):
        transfer(bookings, world, leading=world.cc_b, second=world.cc_a, amount=1000)
    transfer(bookings, world, leading=world.cc_b, second=world.cc_a, amount=500)


def test_budget_transfer_requires_planning_and_planned_cost_centers(
    bookings: BookingService, booking_control: BookingControlService, world: World
) -> None:
    with pytest.raises(ValidationError, match="aktivierter Planung"):
        transfer(bookings, world, leading=world.cc_a, second=world.cc_b)
    enable_planning(booking_control)
    with pytest.raises(ValidationError, match="mit Planung"):
        transfer(bookings, world, leading=world.cc_a, second=world.cc_free)
    with pytest.raises(ValidationError, match="verschieden"):
        transfer(bookings, world, leading=world.cc_a, second=world.cc_a)


# Ändern, Löschen, Stornieren


def _update(bookings: BookingService, world: World, booking_id: str, **changes: object) -> None:
    current = bookings.get_booking(booking_id)
    values: dict[str, object] = {
        "booking_type": current.booking_type,
        "entry_side": current.entry_side,
        "amount_cents": current.amount_cents,
        "booking_date": current.booking_date,
        "origin_date": current.origin_date,
        "leading": cc(current.legs[0].cost_center_id or ""),
        "second": acc(current.legs[1].account_id or ""),
        "merchant": current.merchant,
        "booking_text": current.booking_text,
    }
    values.update(changes)
    bookings.update(booking_id, actor_id=world.actor, **values)  # type: ignore[arg-type]


def test_update_moves_the_effect_to_new_values(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = book(bookings, world, amount=5000)

    _update(
        bookings,
        world,
        booking_id,
        amount_cents=7000,
        entry_side=Side.CREDIT,
        leading=cc(world.cc_b),
        second=acc(world.savings),
        booking_date=date(2026, 6, 2),
        origin_date=date(2026, 6, 2),
    )

    assert actuals(database) == {(world.cc_b, 6): (0, 7000)}
    assert bookings.account_balance(world.giro) == 0
    assert bookings.account_balance(world.savings) == 7000
    assert "BOOKING_UPDATED" in audit_names(database)
    assert booking_count(database) == 1


def test_update_checks_only_the_net_effect(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 1000)
    booking_id = book(bookings, world, amount=1000)
    refund_id = book(bookings, world, side=Side.CREDIT, amount=300)
    book(bookings, world, amount=300)  # Haushaltsrest ist jetzt genau 0

    _update(bookings, world, refund_id, booking_text="nur anderer Text")
    assert bookings.get_booking(refund_id).booking_text == "nur anderer Text"
    with pytest.raises(BudgetExceededError):
        _update(bookings, world, refund_id, amount_cents=100)
    assert bookings.get_booking(refund_id).amount_cents == 300
    assert actuals(database) == {(world.cc_a, 5): (1300, 300)}
    assert booking_id


def test_update_and_delete_are_blocked_in_closed_month(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = book(bookings, world, booking_date=date(2026, 4, 20))
    _close_month(database, world.actor, 2026, 4)

    with pytest.raises(PeriodError, match="Gegenbuchung"):
        _update(bookings, world, booking_id, amount_cents=1)
    with pytest.raises(PeriodError, match="Gegenbuchung"):
        bookings.delete(booking_id, actor_id=world.actor)
    assert bookings.get_booking(booking_id).amount_cents == 5000


def test_delete_takes_back_the_effect(
    bookings: BookingService, database: Database, world: World
) -> None:
    booking_id = book(bookings, world, amount=5000)
    bookings.delete(booking_id, actor_id=world.actor)

    assert actuals(database) == {}
    assert bookings.account_balance(world.giro) == 0
    assert booking_count(database) == 0
    with pytest.raises(NotFoundError):
        bookings.get_booking(booking_id)
    assert "BOOKING_DELETED" in audit_names(database)


def test_deleting_a_refund_is_blocked_when_it_would_exceed_the_budget(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 1000)
    book(bookings, world, amount=1000)
    refund_id = book(bookings, world, side=Side.CREDIT, amount=500)
    book(bookings, world, amount=500)  # Haushaltsrest ist jetzt genau 0
    with pytest.raises(BudgetExceededError):
        bookings.delete(refund_id, actor_id=world.actor)
    assert booking_count(database) == 3


def test_reversal_is_a_minus_booking_on_the_same_side(
    bookings: BookingService, database: Database, world: World
) -> None:
    original_id = book(bookings, world, side=Side.DEBIT, amount=5000)
    reversal_id = bookings.reverse(original_id, booking_date=D, actor_id=world.actor)

    reversal = bookings.get_booking(reversal_id)
    assert reversal.entry_side is Side.DEBIT
    assert reversal.amount_cents == -5000
    assert reversal.reversal_of_id == original_id
    assert reversal.booking_text.startswith("Storno")
    assert actuals(database) == {(world.cc_a, 5): (0, 0)} or actuals(database) == {}
    assert bookings.account_balance(world.giro) == 0

    with pytest.raises(ValidationError, match="bereits storniert"):
        bookings.reverse(original_id, booking_date=D, actor_id=world.actor)
    with pytest.raises(ValidationError, match="nicht erneut"):
        bookings.reverse(reversal_id, booking_date=D, actor_id=world.actor)
    with pytest.raises(ValidationError, match="storniert"):
        _update(bookings, world, original_id, amount_cents=1)
    with pytest.raises(ValidationError, match="storniert"):
        bookings.delete(original_id, actor_id=world.actor)
    with pytest.raises(ValidationError, match="Storno"):
        _update(bookings, world, reversal_id, amount_cents=1)


def test_deleting_the_reversal_restores_the_original(
    bookings: BookingService, database: Database, world: World
) -> None:
    original_id = book(bookings, world, amount=5000)
    reversal_id = bookings.reverse(original_id, booking_date=D, actor_id=world.actor)
    bookings.delete(reversal_id, actor_id=world.actor)

    assert actuals(database) == {(world.cc_a, 5): (5000, 0)}
    bookings.delete(original_id, actor_id=world.actor)


def test_reversal_of_a_closed_month_booking_goes_into_the_open_month(
    bookings: BookingService, database: Database, world: World
) -> None:
    original_id = book(bookings, world, amount=5000, booking_date=date(2026, 4, 20))
    other_id = book(bookings, world, amount=100, booking_date=date(2026, 4, 21))
    _close_month(database, world.actor, 2026, 4)

    reversal_id = bookings.reverse(
        original_id, booking_date=bookings.default_booking_date(), actor_id=world.actor
    )
    assert bookings.get_booking(reversal_id).fiscal_month == 5
    with pytest.raises(PeriodError):
        bookings.reverse(other_id, booking_date=date(2026, 4, 25), actor_id=world.actor)


def test_reversal_of_a_budget_transfer_restores_the_budget(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 10000)
    set_budget(database, world.cc_b, 0)
    transfer_id = transfer(bookings, world, leading=world.cc_a, second=world.cc_b, amount=3000)

    bookings.reverse(transfer_id, booking_date=D, actor_id=world.actor)

    assert bookings.cost_center_info(world.cc_a, D).annual_budget_cents == 10000
    assert bookings.cost_center_info(world.cc_b, D).annual_budget_cents == 0


# Atomarität, Kontrollsumme, Neuaufbau


def test_failure_in_projection_rolls_back_the_whole_booking(
    bookings: BookingService,
    database: Database,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(self: SqlPlanRepository, actual: object) -> None:
        raise RuntimeError("Fortschreibung fehlgeschlagen")

    monkeypatch.setattr(SqlPlanRepository, "save_actual", fail)
    with pytest.raises(RuntimeError):
        book(bookings, world)

    monkeypatch.undo()
    assert booking_count(database) == 0
    assert actuals(database) == {}
    assert "BOOKING_CREATED" not in audit_names(database)


def test_control_sum_of_accounts_equals_cost_center_movement(
    bookings: BookingService, database: Database, world: World
) -> None:
    book(bookings, world, side=Side.DEBIT, amount=5000)
    book(bookings, world, side=Side.DEBIT, amount=-1200, cost_center=world.cc_b)
    book(bookings, world, side=Side.CREDIT, amount=3000, account=world.savings)
    book(bookings, world, side=Side.CREDIT, amount=-700, cost_center=world.cc_free)
    bookings.post_transfer(
        amount_cents=2500,
        booking_date=D,
        origin_date=D,
        leading_cost_center_id=world.cc_a,
        leading_account_id=world.giro,
        transfer_cost_center_id=world.cc_b,
        transfer_account_id=world.savings,
        actor_id=world.actor,
    )

    # Beide Ist-Buchungen auf Kostenstellen ohne Konto-Angabe laufen über das Girokonto
    assert bookings.account_balance(world.giro) == -5000 + 1200 - 700 - 2500
    assert bookings.account_balance(world.savings) == 3000 + 2500
    account_total = bookings.account_balance(world.giro) + bookings.account_balance(world.savings)
    movement = sum(debit - credit for debit, credit in actuals(database).values())
    assert account_total == -movement


def test_rebuild_restores_projections_from_bookings(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 10000)
    set_budget(database, world.cc_b, 0)
    book(bookings, world, amount=4000)
    book(bookings, world, side=Side.CREDIT, amount=500, cost_center=world.cc_b)
    transfer(bookings, world, leading=world.cc_a, second=world.cc_b, amount=2000)
    expected_actuals = actuals(database)
    expected_budget = (
        bookings.cost_center_info(world.cc_a, D).annual_budget_cents,
        bookings.cost_center_info(world.cc_b, D).annual_budget_cents,
    )

    with database.session_factory() as session:
        for row in session.scalars(select(MonthlyActualModel)):
            row.debit_cents, row.credit_cents = 1, 2
        for plan in session.scalars(select(CostCenterPlanModel)):
            plan.budget_transfer_cents = 99
        session.commit()
    assert actuals(database) != expected_actuals

    bookings.rebuild_projections(actor_id=world.actor)

    assert actuals(database) == expected_actuals
    assert (
        bookings.cost_center_info(world.cc_a, D).annual_budget_cents,
        bookings.cost_center_info(world.cc_b, D).annual_budget_cents,
    ) == expected_budget


# Auskunft für den Buchungsdialog


def test_cost_center_info_for_the_booking_dialog(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    enable_planning(booking_control)
    set_budget(database, world.cc_a, 10000)
    with database.session_factory() as session:
        plan = session.scalars(select(CostCenterPlanModel)).one()
        session.add(MonthlyPlanModel(cost_center_plan_id=plan.id, month=5, plan_cents=2500))
        session.commit()
    book(bookings, world, amount=1500)
    book(bookings, world, amount=700, booking_date=date(2026, 6, 1))

    info = bookings.cost_center_info(world.cc_a, D)

    assert info.planning_active is True
    assert info.annual_budget_cents == 10000
    assert info.movement_cents == 2200
    assert info.remaining_cents == 7800
    assert info.month_plan_cents == 2500
    assert info.month_movement_cents == 1500
    assert info.reserve_cents == 0
    assert bookings.cost_center_info(world.cc_free, D).planning_active is False


def test_list_bookings_resolves_labels_and_status(
    bookings: BookingService, database: Database, world: World
) -> None:
    closed_id = book(bookings, world, booking_date=date(2026, 4, 20), text="April")
    open_id = book(bookings, world, text="Mai")
    reversed_id = book(bookings, world, text="zu stornieren")
    reversal_id = bookings.reverse(reversed_id, booking_date=D, actor_id=world.actor)
    _close_month(database, world.actor, 2026, 4)

    views = {view.id: view for view in bookings.list_bookings(year=2026)}

    assert views[closed_id].is_closed and not views[closed_id].can_edit
    assert not views[closed_id].can_delete and views[closed_id].can_reverse
    assert views[open_id].can_edit and views[open_id].can_delete
    assert views[open_id].leading_label == "100 Lebensmittel"
    assert views[open_id].second_label == "1000 Girokonto"
    assert views[reversed_id].is_reversed and not views[reversed_id].can_reverse
    assert views[reversal_id].is_reversal and not views[reversal_id].can_edit
    assert views[reversal_id].can_delete
    assert [v.id for v in bookings.list_bookings(year=2026, month=4)] == [closed_id]
