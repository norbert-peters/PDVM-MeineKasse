import pytest

from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.services.booking_rules import (
    Stelle,
    balance_effect,
    build_legs,
    movement_effect,
    validate_amount,
)

COST_CENTER = Stelle(ObjectKind.COST_CENTER, "cc-1")
OTHER_COST_CENTER = Stelle(ObjectKind.COST_CENTER, "cc-2")
ACCOUNT = Stelle(ObjectKind.ACCOUNT, "acc-1")
OTHER_ACCOUNT = Stelle(ObjectKind.ACCOUNT, "acc-2")


@pytest.mark.parametrize("side", [Side.DEBIT, Side.CREDIT])
def test_actual_booking_is_aligned_on_both_stellen(side: Side) -> None:
    first, second = build_legs(BookingType.COST_CENTER_TO_ACCOUNT, side, COST_CENTER, ACCOUNT)
    assert (first.side, second.side) == (side, side)
    assert (first.position, second.position) == (1, 2)


@pytest.mark.parametrize("side", [Side.DEBIT, Side.CREDIT])
def test_account_transfer_is_opposed(side: Side) -> None:
    first, second = build_legs(BookingType.ACCOUNT_TO_ACCOUNT, side, ACCOUNT, OTHER_ACCOUNT)
    assert first.side is side
    assert second.side is not side


def test_budget_transfer_is_opposed() -> None:
    first, second = build_legs(
        BookingType.BUDGET_TRANSFER, Side.DEBIT, COST_CENTER, OTHER_COST_CENTER
    )
    assert (first.side, second.side) == (Side.DEBIT, Side.CREDIT)


def test_stellen_must_match_booking_type() -> None:
    with pytest.raises(ValidationError):
        build_legs(BookingType.COST_CENTER_TO_ACCOUNT, Side.DEBIT, ACCOUNT, COST_CENTER)
    with pytest.raises(ValidationError):
        build_legs(BookingType.BUDGET_TRANSFER, Side.DEBIT, COST_CENTER, ACCOUNT)


def test_stellen_must_differ() -> None:
    with pytest.raises(ValidationError):
        build_legs(BookingType.ACCOUNT_TO_ACCOUNT, Side.DEBIT, ACCOUNT, ACCOUNT)


def test_amount_zero_is_rejected_but_negative_is_allowed() -> None:
    validate_amount(-50)
    validate_amount(50)
    with pytest.raises(ValidationError):
        validate_amount(0)


def test_debit_reduces_balance_and_increases_movement() -> None:
    assert balance_effect(Side.DEBIT, 5000) == -5000
    assert movement_effect(Side.DEBIT, 5000) == 5000


def test_credit_increases_balance_and_reduces_movement() -> None:
    assert balance_effect(Side.CREDIT, 2000) == 2000
    assert movement_effect(Side.CREDIT, 2000) == -2000


def test_negative_debit_stays_a_debit_booking_but_relieves() -> None:
    """Soll -50 € ist eine negative Ausgabe: Saldo steigt, Seite bleibt Soll."""
    assert balance_effect(Side.DEBIT, -5000) == 5000
    assert movement_effect(Side.DEBIT, -5000) == -5000


def test_negative_debit_and_positive_credit_have_same_effect_but_stay_distinct() -> None:
    assert balance_effect(Side.DEBIT, -2000) == balance_effect(Side.CREDIT, 2000)
