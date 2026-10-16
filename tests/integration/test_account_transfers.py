from datetime import date

import pytest
from sqlalchemy import func, select

from conftest import World
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import BudgetExceededError, NotFoundError, ValidationError
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.infrastructure.database.models import (
    BookingLegModel,
    BookingModel,
    CostCenterPlanModel,
)
from meine_kasse.infrastructure.database.session import Database

D = date(2026, 5, 10)
YEAR = 2026


def post_transfer(
    bookings: BookingService, world: World, *, amount: int = 2500, same_cost_center: bool = False
) -> str:
    return bookings.post_transfer(
        amount_cents=amount,
        booking_date=D,
        origin_date=D,
        leading_cost_center_id=world.cc_a,
        leading_account_id=world.giro,
        transfer_cost_center_id=world.cc_a if same_cost_center else world.cc_b,
        transfer_account_id=world.savings,
        merchant="Bank",
        booking_text="Sparrate",
        actor_id=world.actor,
    )


def update_transfer(
    bookings: BookingService, world: World, transfer_id: str, *, amount: int
) -> None:
    bookings.update_transfer(
        transfer_id,
        amount_cents=amount,
        booking_date=D,
        origin_date=D,
        leading_cost_center_id=world.cc_a,
        leading_account_id=world.giro,
        transfer_cost_center_id=world.cc_b,
        transfer_account_id=world.savings,
        actor_id=world.actor,
    )


def movement(bookings: BookingService, cost_center_id: str) -> int:
    return bookings.cost_center_info(cost_center_id, D).movement_cents


def booking_count(database: Database) -> int:
    with database.session_factory() as session:
        return session.scalar(select(func.count()).select_from(BookingModel)) or 0


def test_transfer_is_split_into_two_bookings_with_a_cost_center_each(
    bookings: BookingService, world: World
) -> None:
    transfer_id = post_transfer(bookings, world, amount=2500)

    debit, credit = bookings.get_transfer(transfer_id)
    assert debit.transfer_id == credit.transfer_id == transfer_id
    assert debit.booking_type is credit.booking_type is BookingType.COST_CENTER_TO_ACCOUNT
    assert (debit.entry_side, credit.entry_side) == (Side.DEBIT, Side.CREDIT)
    assert debit.amount_cents == credit.amount_cents == 2500
    assert [leg.side for leg in debit.legs] == [Side.DEBIT, Side.DEBIT]
    assert [leg.side for leg in credit.legs] == [Side.CREDIT, Side.CREDIT]
    assert (debit.legs[0].cost_center_id, debit.legs[1].account_id) == (world.cc_a, world.giro)
    assert (credit.legs[0].cost_center_id, credit.legs[1].account_id) == (
        world.cc_b,
        world.savings,
    )

    assert bookings.account_balance(world.giro) == -2500
    assert bookings.account_balance(world.savings) == 2500
    assert movement(bookings, world.cc_a) == 2500
    assert movement(bookings, world.cc_b) == -2500


def test_transfer_with_the_same_cost_center_is_neutral(
    bookings: BookingService, world: World
) -> None:
    post_transfer(bookings, world, amount=2500, same_cost_center=True)

    assert movement(bookings, world.cc_a) == 0
    assert bookings.account_balance(world.giro) == -2500
    assert bookings.account_balance(world.savings) == 2500


def test_transfer_needs_two_different_accounts_and_an_amount(
    bookings: BookingService, database: Database, world: World
) -> None:
    with pytest.raises(ValidationError, match="verschieden"):
        bookings.post_transfer(
            amount_cents=100,
            booking_date=D,
            origin_date=D,
            leading_cost_center_id=world.cc_a,
            leading_account_id=world.giro,
            transfer_cost_center_id=world.cc_b,
            transfer_account_id=world.giro,
            actor_id=world.actor,
        )
    with pytest.raises(ValidationError, match="0"):
        post_transfer(bookings, world, amount=0)
    assert booking_count(database) == 0


def test_account_to_account_can_no_longer_be_posted(
    bookings: BookingService, database: Database, world: World
) -> None:
    with pytest.raises(ValidationError, match="Kostenstelle"):
        bookings.post(
            booking_type=BookingType.ACCOUNT_TO_ACCOUNT,
            entry_side=Side.DEBIT,
            amount_cents=100,
            booking_date=D,
            origin_date=D,
            leading=Stelle(ObjectKind.ACCOUNT, world.giro),
            second=Stelle(ObjectKind.ACCOUNT, world.savings),
            actor_id=world.actor,
        )
    assert booking_count(database) == 0


def test_budget_lock_rejects_the_whole_transfer(
    bookings: BookingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    booking_control.update(planning_enabled=True, current_year=YEAR, current_month=5)
    with database.session_factory() as session:
        for cost_center_id, cents in ((world.cc_a, 1000), (world.cc_b, 0)):
            session.add(
                CostCenterPlanModel(
                    cost_center_id=cost_center_id, year=YEAR, base_budget_cents=cents
                )
            )
        session.commit()

    with pytest.raises(BudgetExceededError):
        post_transfer(bookings, world, amount=5000)

    assert booking_count(database) == 0
    assert bookings.account_balance(world.giro) == 0
    assert bookings.account_balance(world.savings) == 0


def test_update_changes_both_bookings_and_halves_cannot_be_edited_alone(
    bookings: BookingService, world: World
) -> None:
    transfer_id = post_transfer(bookings, world, amount=2500)

    update_transfer(bookings, world, transfer_id, amount=4000)

    debit, credit = bookings.get_transfer(transfer_id)
    assert debit.amount_cents == credit.amount_cents == 4000
    assert bookings.account_balance(world.giro) == -4000
    assert bookings.account_balance(world.savings) == 4000
    assert movement(bookings, world.cc_a) == 4000
    assert movement(bookings, world.cc_b) == -4000
    with pytest.raises(ValidationError, match="Umbuchung"):
        bookings.update(
            debit.id,
            booking_type=debit.booking_type,
            entry_side=debit.entry_side,
            amount_cents=1,
            booking_date=D,
            origin_date=D,
            leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
            second=Stelle(ObjectKind.ACCOUNT, world.giro),
            actor_id=world.actor,
        )


def test_deleting_one_half_deletes_the_whole_transfer(
    bookings: BookingService, database: Database, world: World
) -> None:
    transfer_id = post_transfer(bookings, world)
    debit, _credit = bookings.get_transfer(transfer_id)

    bookings.delete(debit.id, actor_id=world.actor)

    assert booking_count(database) == 0
    assert bookings.account_balance(world.giro) == 0
    assert bookings.account_balance(world.savings) == 0
    assert movement(bookings, world.cc_a) == movement(bookings, world.cc_b) == 0
    with pytest.raises(NotFoundError):
        bookings.get_transfer(transfer_id)


def test_reversing_one_half_reverses_the_whole_transfer(
    bookings: BookingService, database: Database, world: World
) -> None:
    transfer_id = post_transfer(bookings, world, amount=2500)
    debit, credit = bookings.get_transfer(transfer_id)

    reversal_id = bookings.reverse(credit.id, booking_date=D, actor_id=world.actor)

    reversal = bookings.get_booking(reversal_id)
    assert reversal.reversal_of_id == credit.id
    assert reversal.entry_side is Side.CREDIT and reversal.amount_cents == -2500
    assert reversal.transfer_id is not None and reversal.transfer_id != transfer_id
    reversal_debit, reversal_credit = bookings.get_transfer(reversal.transfer_id)
    assert reversal_debit.reversal_of_id == debit.id
    assert reversal_credit.id == reversal_id
    assert bookings.account_balance(world.giro) == 0
    assert bookings.account_balance(world.savings) == 0
    assert movement(bookings, world.cc_a) == movement(bookings, world.cc_b) == 0
    with pytest.raises(ValidationError, match="storniert"):
        bookings.reverse(debit.id, booking_date=D, actor_id=world.actor)

    bookings.delete(reversal_id, actor_id=world.actor)
    assert booking_count(database) == 2
    assert bookings.account_balance(world.giro) == -2500


def test_list_bookings_shows_both_bookings_of_a_transfer(
    bookings: BookingService, world: World
) -> None:
    transfer_id = post_transfer(bookings, world)

    views = [view for view in bookings.list_bookings(year=2026) if view.transfer_id == transfer_id]

    assert [(view.entry_side, view.leading_label, view.second_label) for view in views] == [
        (Side.DEBIT, "100 Lebensmittel", "1000 Girokonto"),
        (Side.CREDIT, "200 Reisen", "2000 Sparkonto"),
    ]


def test_legacy_account_to_account_booking_can_still_be_reversed(
    bookings: BookingService, database: Database, world: World
) -> None:
    with database.session_factory() as session:
        booking = BookingModel(
            origin_date=D,
            booking_date=D,
            booking_type=BookingType.ACCOUNT_TO_ACCOUNT.value,
            entry_side=Side.DEBIT.value,
            amount_cents=700,
            fiscal_year=2026,
            fiscal_month=5,
            created_by_user_id=world.actor,
        )
        session.add(booking)
        session.flush()
        session.add_all(
            [
                BookingLegModel(
                    booking_id=booking.id,
                    position=1,
                    side=Side.DEBIT.value,
                    account_id=world.giro,
                ),
                BookingLegModel(
                    booking_id=booking.id,
                    position=2,
                    side=Side.CREDIT.value,
                    account_id=world.savings,
                ),
            ]
        )
        session.commit()
        legacy_id = booking.id

    view = next(v for v in bookings.list_bookings(year=2026) if v.id == legacy_id)
    assert not view.can_edit and view.can_reverse
    bookings.reverse(legacy_id, booking_date=D, actor_id=world.actor)

    assert bookings.account_balance(world.giro) == 0
    assert bookings.account_balance(world.savings) == 0
