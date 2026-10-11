from dataclasses import replace
from datetime import date

import pytest

from meine_kasse.domain.entities import Booking, BookingLeg, MonthlyPlan
from meine_kasse.domain.enums import BookingType, PlanMode, Side
from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.services.closing_rules import (
    month_signature,
    next_period,
    projection_mismatches,
    year_signature,
)


def make_booking(booking_id: str = "b1", **changes: object) -> Booking:
    booking = Booking(
        id=booking_id,
        name="x",
        origin_date=date(2026, 5, 1),
        booking_date=date(2026, 5, 2),
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=Side.DEBIT,
        amount_cents=5000,
        merchant="Markt",
        booking_text="Einkauf",
        reversal_of_id=None,
        fiscal_year=2026,
        fiscal_month=5,
        created_by_user_id="u",
        legs=(
            BookingLeg(1, Side.DEBIT, "cc", None),
            BookingLeg(2, Side.DEBIT, None, "acc"),
        ),
    )
    return replace(booking, **changes)  # type: ignore[arg-type]


def plan(cost_center: str = "cc", month: int = 5, cents: int = 1000) -> tuple[str, MonthlyPlan]:
    return cost_center, MonthlyPlan("p", "plan", month, cents, 0, PlanMode.MONTHLY)


def test_next_period_wraps_the_year() -> None:
    assert next_period(2026, 5) == (2026, 6)
    assert next_period(2026, 12) == (2027, 1)


def test_signature_is_a_stable_sha256_hex_digest() -> None:
    signature = month_signature(2026, 5, [make_booking()], [plan()])
    assert len(signature) == 64
    assert int(signature, 16) >= 0
    assert signature == month_signature(2026, 5, [make_booking()], [plan()])


def test_signature_does_not_depend_on_input_order() -> None:
    first, second = make_booking("a"), make_booking("b", amount_cents=100)
    assert month_signature(2026, 5, [first, second], [plan("x"), plan("y")]) == month_signature(
        2026, 5, [second, first], [plan("y"), plan("x")]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"amount_cents": 5001},
        {"amount_cents": -5000},
        {"entry_side": Side.CREDIT},
        {"booking_date": date(2026, 5, 3)},
        {"booking_text": "anders"},
        {"merchant": "anders"},
        {"reversal_of_id": "x"},
        {"booking_type": BookingType.ACCOUNT_TO_ACCOUNT},
        {
            "legs": (
                BookingLeg(1, Side.DEBIT, "cc2", None),
                BookingLeg(2, Side.DEBIT, None, "acc"),
            )
        },
    ],
)
def test_signature_detects_any_change_of_a_booking(changes: dict[str, object]) -> None:
    original = month_signature(2026, 5, [make_booking()], [])
    assert month_signature(2026, 5, [make_booking(**changes)], []) != original


def test_signature_detects_added_or_removed_bookings_and_plan_changes() -> None:
    base = month_signature(2026, 5, [make_booking()], [plan()])
    assert month_signature(2026, 5, [make_booking(), make_booking("b2")], [plan()]) != base
    assert month_signature(2026, 5, [], [plan()]) != base
    assert month_signature(2026, 5, [make_booking()], [plan(cents=1001)]) != base
    assert month_signature(2026, 5, [make_booking()], []) != base
    assert month_signature(2026, 6, [make_booking()], [plan()]) != base


def test_signature_ignores_plans_of_other_months() -> None:
    base = month_signature(2026, 5, [make_booking()], [plan(month=5)])
    assert month_signature(2026, 5, [make_booking()], [plan(month=5), plan(month=6)]) == base


def test_year_signature_needs_all_twelve_months() -> None:
    signatures = {month: f"{month:064d}" for month in range(1, 13)}
    first = year_signature(2026, signatures)
    assert len(first) == 64
    changed = dict(signatures)
    changed[7] = "f" * 64
    assert year_signature(2026, changed) != first
    assert year_signature(2027, signatures) != first
    with pytest.raises(ValidationError):
        year_signature(2026, {1: "a" * 64})


def test_projection_mismatches_lists_only_differing_cost_centers() -> None:
    booked = {"a": (100, 0), "b": (0, 50), "c": (10, 10)}
    projected = {"a": (100, 0), "b": (0, 40), "d": (5, 0)}
    assert projection_mismatches(booked, projected) == ["b", "c", "d"]
    assert projection_mismatches({"a": (0, 0)}, {}) == []
