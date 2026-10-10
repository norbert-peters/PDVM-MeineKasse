import pytest

from meine_kasse.domain.enums import CostCenterKind
from meine_kasse.domain.errors import BudgetExceededError, ValidationError
from meine_kasse.domain.services.budget_rules import (
    BudgetPosition,
    check_actual_booking,
    check_budget_change,
    validate_budget_transfer_allowed,
)

STANDARD = CostCenterKind.STANDARD


def position(budget: int = 10000, movement: int = 0, distributed: int = 0) -> BudgetPosition:
    return BudgetPosition(budget, movement, distributed)


def test_remaining_is_budget_minus_movement() -> None:
    assert position(10000, 2500).remaining_cents == 7500
    assert position(10000, -500).remaining_cents == 10500


def test_booking_up_to_remaining_is_allowed() -> None:
    check_actual_booking(position(), 10000, planning_enabled=True, kind=STANDARD)


def test_booking_one_cent_over_remaining_is_blocked() -> None:
    with pytest.raises(BudgetExceededError) as error:
        check_actual_booking(position(), 10001, planning_enabled=True, kind=STANDARD)
    assert error.value.shortfall_cents == 1
    assert "0,01 €" in str(error.value)


def test_relieving_bookings_are_never_blocked() -> None:
    exhausted = position(10000, 12000)
    check_actual_booking(exhausted, -1, planning_enabled=True, kind=STANDARD)
    check_actual_booking(exhausted, 0, planning_enabled=True, kind=STANDARD)


def test_booking_is_not_checked_without_plan_or_with_planning_disabled() -> None:
    check_actual_booking(
        position(0), 99999, planning_enabled=True, kind=CostCenterKind.WITHOUT_PLAN
    )
    check_actual_booking(position(0), 99999, planning_enabled=False, kind=STANDARD)


def test_increasing_budget_is_always_allowed() -> None:
    check_budget_change(position(0, 5000), 100)


def test_giving_away_free_budget_is_allowed() -> None:
    check_budget_change(position(10000, 3000, 4000), -6000)


def test_giving_away_more_than_distributed_or_used_is_blocked() -> None:
    with pytest.raises(BudgetExceededError) as error:
        check_budget_change(position(10000, 3000, 4000), -6001)
    assert error.value.shortfall_cents == 1
    assert "60,00 €" in str(error.value)


def test_budget_cannot_fall_below_movement() -> None:
    with pytest.raises(BudgetExceededError):
        check_budget_change(position(10000, 8000, 0), -2001)


def test_budget_cannot_become_negative_when_movement_is_negative() -> None:
    with pytest.raises(BudgetExceededError):
        check_budget_change(position(1000, -5000, 0), -1001)


def test_transfer_requires_planning_and_standard_cost_centers() -> None:
    validate_budget_transfer_allowed(planning_enabled=True, kinds=(STANDARD, STANDARD))
    with pytest.raises(ValidationError):
        validate_budget_transfer_allowed(planning_enabled=False, kinds=(STANDARD, STANDARD))
    with pytest.raises(ValidationError):
        validate_budget_transfer_allowed(
            planning_enabled=True, kinds=(STANDARD, CostCenterKind.WITHOUT_PLAN)
        )
