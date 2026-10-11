from datetime import date

from meine_kasse.domain.entities import AccountOpeningBalance, Booking, BookingLeg
from meine_kasse.domain.enums import BookingType, Side
from meine_kasse.domain.services.closing_rules import month_signature
from meine_kasse.domain.services.opening_rules import (
    OpeningSource,
    OpeningState,
    is_january_closed,
    opening_editability,
    opening_for_year,
    opening_source,
)


def manual(year: int = 2026, cents: int = 10000) -> AccountOpeningBalance:
    return AccountOpeningBalance("o", "acc", year, cents)


def state(
    *,
    year: int = 2026,
    opening: AccountOpeningBalance | None = None,
    prior: bool = False,
    months: set[tuple[int, int]] | None = None,
    years: set[int] | None = None,
) -> OpeningState:
    return opening_editability(
        year=year,
        manual=opening,
        has_bookings_before_year=prior,
        closed_months=months or set(),
        closed_years=years or set(),
    ).state


def test_opening_is_editable_without_prior_year_while_january_is_open() -> None:
    assert state() is OpeningState.EDITABLE
    assert state(opening=manual()) is OpeningState.EDITABLE
    assert state(months={(2026, 2), (2025, 1)}) is OpeningState.EDITABLE


def test_closing_january_or_the_year_locks_the_opening() -> None:
    assert state(months={(2026, 1)}) is OpeningState.LOCKED
    assert state(years={2026}) is OpeningState.LOCKED
    assert is_january_closed(2026, {(2026, 1)}, set())
    assert not is_january_closed(2026, {(2026, 2)}, set())


def test_a_prior_year_makes_the_opening_derived() -> None:
    assert state(prior=True) is OpeningState.CARRIED
    assert state(opening=manual(2025)) is OpeningState.CARRIED


def test_locked_wins_over_carried() -> None:
    assert state(prior=True, months={(2026, 1)}) is OpeningState.LOCKED


def test_moving_an_opening_to_another_year_depends_on_the_old_year() -> None:
    editability = opening_editability(
        year=2026,
        manual=manual(2027),
        has_bookings_before_year=False,
        closed_months=set(),
        closed_years=set(),
    )
    assert editability.state is OpeningState.EDITABLE
    assert "2027" in editability.message
    assert state(year=2026, opening=manual(2027), months={(2027, 1)}) is OpeningState.LOCKED


def test_opening_for_year_adds_the_manual_amount_and_earlier_movements() -> None:
    assert (
        opening_for_year(year=2026, manual=manual(2026, 10000), movements_before_year_cents=0)
        == 10000
    )
    assert (
        opening_for_year(year=2027, manual=manual(2026, 10000), movements_before_year_cents=-2500)
        == 7500
    )
    assert opening_for_year(year=2026, manual=manual(2027, 999), movements_before_year_cents=0) == 0
    assert opening_for_year(year=2026, manual=None, movements_before_year_cents=0) == 0


def test_opening_source() -> None:
    assert (
        opening_source(year=2026, manual=manual(2026), has_bookings_before_year=False)
        is OpeningSource.MANUAL
    )
    assert (
        opening_source(year=2027, manual=manual(2026), has_bookings_before_year=False)
        is OpeningSource.CARRIED
    )
    assert (
        opening_source(year=2027, manual=None, has_bookings_before_year=True)
        is OpeningSource.CARRIED
    )
    assert (
        opening_source(year=2026, manual=None, has_bookings_before_year=False) is OpeningSource.NONE
    )


def make_booking() -> Booking:
    return Booking(
        id="b1",
        name="x",
        origin_date=date(2026, 1, 1),
        booking_date=date(2026, 1, 2),
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=Side.DEBIT,
        amount_cents=100,
        merchant="",
        booking_text="",
        reversal_of_id=None,
        fiscal_year=2026,
        fiscal_month=1,
        created_by_user_id="u",
        legs=(BookingLeg(1, Side.DEBIT, "cc", None), BookingLeg(2, Side.DEBIT, None, "acc")),
    )


def test_january_signature_covers_openings_but_stays_stable_without_them() -> None:
    bookings = [make_booking()]
    plain = month_signature(2026, 1, bookings, [])
    assert month_signature(2026, 1, bookings, [], []) == plain
    assert month_signature(2026, 1, bookings, [], [manual(2025)]) == plain

    with_opening = month_signature(2026, 1, bookings, [], [manual(2026, 10000)])
    assert with_opening != plain
    assert month_signature(2026, 1, bookings, [], [manual(2026, 10001)]) != with_opening
    assert month_signature(2026, 2, bookings, [], [manual(2026, 10000)]) == month_signature(
        2026, 2, bookings, []
    )
