from datetime import date

import pytest
from sqlalchemy import select

from conftest import World
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.application.services.opening_balance_service import (
    OpeningBalanceRow,
    OpeningBalanceService,
)
from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import NotFoundError, ValidationError
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.domain.services.opening_rules import OpeningSource, OpeningState
from meine_kasse.infrastructure.database.models import (
    AccountOpeningBalanceModel,
    AuditLogModel,
)
from meine_kasse.infrastructure.database.session import Database

REASON = "Korrektur nach Pruefung der Kontoauszuege"


def start_in(control: BookingControlService, month: int, year: int = 2026) -> None:
    control.update(planning_enabled=False, current_year=year, current_month=month)


def spend(
    bookings: BookingService,
    world: World,
    day: date,
    cents: int = 5000,
    side: Side = Side.DEBIT,
    account: str | None = None,
) -> str:
    return bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=side,
        amount_cents=cents,
        booking_date=day,
        origin_date=day,
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, account or world.giro),
        actor_id=world.actor,
    )


def row(openings: OpeningBalanceService, year: int, account_id: str) -> OpeningBalanceRow:
    return next(r for r in openings.get_overview(year) if r.account_id == account_id)


def audit_names(database: Database) -> list[str]:
    with database.session_factory() as session:
        return [e.name for e in session.scalars(select(AuditLogModel))]


def test_opening_balance_is_part_of_the_account_balance(
    openings: OpeningBalanceService, bookings: BookingService, world: World
) -> None:
    openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)
    assert bookings.account_balance(world.giro) == 100000

    spend(bookings, world, date(2026, 5, 10), 5000)
    spend(bookings, world, date(2026, 5, 11), 2000, side=Side.CREDIT)

    assert bookings.account_balance(world.giro) == 100000 - 5000 + 2000
    assert bookings.account_balance(world.savings) == 0
    current = row(openings, 2026, world.giro)
    assert current.opening_cents == 100000
    assert current.movement_cents == -3000
    assert current.balance_cents == 97000
    assert current.source is OpeningSource.MANUAL and current.editable


def test_opening_balance_may_be_negative(
    openings: OpeningBalanceService, bookings: BookingService, world: World
) -> None:
    openings.set_opening_balance(world.giro, 2026, -25050, actor_id=world.actor)
    assert bookings.account_balance(world.giro) == -25050
    assert row(openings, 2026, world.giro).opening_cents == -25050


def test_opening_can_be_changed_and_cleared_and_is_audited(
    openings: OpeningBalanceService, bookings: BookingService, database: Database, world: World
) -> None:
    openings.set_opening_balance(world.giro, 2026, 1000, actor_id=world.actor)
    openings.set_opening_balance(world.giro, 2026, 2000, actor_id=world.actor)
    openings.set_opening_balance(world.giro, 2026, 2000, actor_id=world.actor)
    assert bookings.account_balance(world.giro) == 2000
    assert audit_names(database).count("ACCOUNT_OPENING_SET") == 2
    with database.session_factory() as session:
        entries = [
            e for e in session.scalars(select(AuditLogModel)) if e.name == "ACCOUNT_OPENING_SET"
        ]
    assert entries[1].old_value == "2026: 10,00 €"
    assert "20,00 €" in (entries[1].new_value or "")

    openings.clear_opening_balance(world.giro, 2026, actor_id=world.actor)
    assert bookings.account_balance(world.giro) == 0
    assert row(openings, 2026, world.giro).source is OpeningSource.NONE
    assert "ACCOUNT_OPENING_CLEARED" in audit_names(database)
    openings.clear_opening_balance(world.giro, 2026, actor_id=world.actor)


def test_following_year_derives_its_opening_and_is_not_editable(
    openings: OpeningBalanceService, bookings: BookingService, world: World
) -> None:
    openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)
    spend(bookings, world, date(2026, 5, 10), 5000)

    carried = row(openings, 2027, world.giro)
    assert carried.opening_cents == 95000
    assert carried.source is OpeningSource.CARRIED
    assert carried.editability.state is OpeningState.CARRIED and not carried.editable
    with pytest.raises(ValidationError, match="Vorjahr"):
        openings.set_opening_balance(world.giro, 2027, 1, actor_id=world.actor)
    with pytest.raises(ValidationError, match="Vorjahr"):
        openings.clear_opening_balance(world.giro, 2027, actor_id=world.actor)

    fresh = row(openings, 2027, world.savings)
    assert fresh.source is OpeningSource.NONE and fresh.editable
    openings.set_opening_balance(world.savings, 2027, 7000, actor_id=world.actor)
    assert row(openings, 2027, world.savings).opening_cents == 7000


def test_chain_of_years_carries_movements_forward(
    openings: OpeningBalanceService,
    bookings: BookingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)
    spend(bookings, world, date(2026, 5, 10), 5000)
    start_in(booking_control, 1, 2027)
    spend(bookings, world, date(2027, 1, 10), 1000, side=Side.CREDIT)

    assert row(openings, 2027, world.giro).opening_cents == 95000
    assert row(openings, 2027, world.giro).balance_cents == 96000
    assert row(openings, 2028, world.giro).opening_cents == 96000


def test_bookings_before_the_opening_year_are_rejected(
    openings: OpeningBalanceService,
    bookings: BookingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    start_in(booking_control, 1)
    openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)

    with pytest.raises(ValidationError, match="01.01.2026"):
        spend(bookings, world, date(2025, 12, 15))
    spend(bookings, world, date(2025, 12, 15), account=world.savings)
    spend(bookings, world, date(2026, 1, 15))


def test_opening_cannot_be_set_when_the_account_already_has_a_prior_year(
    openings: OpeningBalanceService,
    bookings: BookingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    start_in(booking_control, 12, 2025)
    spend(bookings, world, date(2025, 12, 10), 5000)

    with pytest.raises(ValidationError, match="Vorjahr"):
        openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)
    openings.set_opening_balance(world.giro, 2025, 100000, actor_id=world.actor)
    assert row(openings, 2026, world.giro).opening_cents == 95000


def test_closing_january_locks_the_opening_and_reopening_unlocks_it(
    openings: OpeningBalanceService,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    start_in(booking_control, 1)
    openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)
    closing.close_month(actor_id=world.actor)

    locked = row(openings, 2026, world.giro)
    assert locked.editability.state is OpeningState.LOCKED and not locked.editable
    with pytest.raises(ValidationError, match="Januar 2026"):
        openings.set_opening_balance(world.giro, 2026, 1, actor_id=world.actor)
    with pytest.raises(ValidationError, match="Januar 2026"):
        openings.clear_opening_balance(world.giro, 2026, actor_id=world.actor)
    assert row(openings, 2026, world.savings).editable is False

    closing.reopen_month(2026, 1, reason=REASON, actor_id=world.actor)

    assert row(openings, 2026, world.giro).editable is True
    openings.set_opening_balance(world.giro, 2026, 120000, actor_id=world.actor)


def test_opening_can_move_to_an_earlier_year_while_its_january_is_open(
    openings: OpeningBalanceService,
    bookings: BookingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    start_in(booking_control, 1, 2027)
    openings.set_opening_balance(world.giro, 2027, 100000, actor_id=world.actor)
    moved = row(openings, 2026, world.giro)
    assert moved.editable and "verschiebt" in moved.editability.message

    openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)

    assert row(openings, 2027, world.giro).source is OpeningSource.CARRIED
    assert row(openings, 2027, world.giro).opening_cents == 100000
    start_in(booking_control, 1, 2026)
    spend(bookings, world, date(2026, 1, 15))
    with pytest.raises(ValidationError, match="01.01.2026"):
        spend(bookings, world, date(2025, 12, 31))


def test_opening_cannot_move_when_its_january_is_closed(
    openings: OpeningBalanceService,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    start_in(booking_control, 1, 2027)
    openings.set_opening_balance(world.giro, 2027, 100000, actor_id=world.actor)
    closing.close_month(actor_id=world.actor)

    with pytest.raises(ValidationError, match="2027"):
        openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)


def test_january_signature_detects_a_changed_opening(
    openings: OpeningBalanceService,
    closing: ClosingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    start_in(booking_control, 1)
    openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)
    closing.close_month(actor_id=world.actor)
    assert [c.ok for c in closing.verify_closures()] == [True]

    with database.session_factory() as session:
        session.scalars(select(AccountOpeningBalanceModel)).one().amount_cents = 1
        session.commit()

    assert [c.ok for c in closing.verify_closures()] == [False]


def test_unknown_account_and_invalid_year(
    openings: OpeningBalanceService, master_data: MasterDataService, world: World
) -> None:
    with pytest.raises(NotFoundError):
        openings.set_opening_balance("unbekannt", 2026, 1, actor_id=world.actor)
    with pytest.raises(ValidationError, match="Jahr"):
        openings.set_opening_balance(world.giro, 1800, 1, actor_id=world.actor)
    with pytest.raises(ValidationError, match="Jahr"):
        openings.get_overview(2300)


def test_overview_lists_inactive_accounts(
    openings: OpeningBalanceService, master_data: MasterDataService, world: World
) -> None:
    master_data.set_account_active(world.savings, False)
    rows = {r.account_id: r for r in openings.get_overview(2026)}
    assert rows[world.savings].is_active is False
    assert rows[world.giro].label == "1000 Girokonto"
    assert len(rows) == 2
