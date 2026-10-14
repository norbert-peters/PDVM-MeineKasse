import pytest

from meine_kasse.domain.enums import CostCenterKind, IncomeMode
from meine_kasse.domain.errors import BudgetExceededError, ValidationError
from meine_kasse.domain.services.budget_rules import validate_budget_transfer_allowed
from meine_kasse.domain.services.income_rules import (
    IncomePosition,
    check_coverage,
    check_pass_on,
    passed_on_cents,
)

STANDARD, INCOME = CostCenterKind.STANDARD, CostCenterKind.INCOME


def position(mode: IncomeMode, planned: int, realized: int, passed_on: int = 0) -> IncomePosition:
    return IncomePosition(mode, planned, realized, passed_on)


def test_plan_mode_makes_the_plan_available_but_at_least_the_booked_income() -> None:
    assert position(IncomeMode.PLAN, 10000, 0).available_cents == 10000
    assert position(IncomeMode.PLAN, 10000, 4000).available_cents == 10000
    assert position(IncomeMode.PLAN, 10000, 12000).available_cents == 12000


def test_actual_mode_makes_only_the_booked_income_available() -> None:
    assert position(IncomeMode.ACTUAL, 10000, 0).available_cents == 0
    assert position(IncomeMode.ACTUAL, 10000, 4000).available_cents == 4000


def test_negative_realized_income_is_never_available() -> None:
    assert position(IncomeMode.ACTUAL, 0, -500).available_cents == 0
    assert position(IncomeMode.PLAN, 3000, -500).available_cents == 3000


def test_free_amount_is_available_minus_passed_on_and_never_negative() -> None:
    assert position(IncomeMode.PLAN, 10000, 0, 2500).free_cents == 7500
    assert position(IncomeMode.ACTUAL, 0, 1000, 5000).free_cents == 0


def test_open_expected_income_is_plan_minus_realized() -> None:
    assert position(IncomeMode.PLAN, 10000, 4000).open_expected_cents == 6000
    assert position(IncomeMode.PLAN, 10000, 12000).open_expected_cents == 0
    assert position(IncomeMode.PLAN, 10000, -50).open_expected_cents == 10000


def test_passed_on_is_the_negative_budget_transfer() -> None:
    assert passed_on_cents(-2500) == 2500
    assert passed_on_cents(0) == 0
    assert passed_on_cents(100) == 0


def test_pass_on_is_limited_to_the_free_amount() -> None:
    check_pass_on(position(IncomeMode.PLAN, 10000, 0, 2500), -7500)
    with pytest.raises(BudgetExceededError, match="höchstens 75,00 €") as error:
        check_pass_on(position(IncomeMode.PLAN, 10000, 0, 2500), -7501)
    assert error.value.shortfall_cents == 1


def test_a_budget_increase_of_the_income_is_not_checked() -> None:
    check_pass_on(position(IncomeMode.ACTUAL, 0, 0, 500), 500)


def test_coverage_fails_when_passed_on_exceeds_the_available_amount() -> None:
    check_coverage(position(IncomeMode.ACTUAL, 0, 5000, 5000), reason="x")
    with pytest.raises(BudgetExceededError, match="Grund") as error:
        check_coverage(position(IncomeMode.ACTUAL, 0, 4999, 5000), reason="Grund")
    assert error.value.shortfall_cents == 1


def test_income_can_only_give_budget_to_standard() -> None:
    validate_budget_transfer_allowed(planning_enabled=True, kinds=(INCOME, STANDARD))
    validate_budget_transfer_allowed(
        planning_enabled=True, kinds=(STANDARD, INCOME), donor_is_leading=False
    )
    with pytest.raises(ValidationError, match="nicht erhalten"):
        validate_budget_transfer_allowed(planning_enabled=True, kinds=(STANDARD, INCOME))
    with pytest.raises(ValidationError, match="nicht erhalten"):
        validate_budget_transfer_allowed(
            planning_enabled=True, kinds=(INCOME, STANDARD), donor_is_leading=False
        )
    with pytest.raises(ValidationError, match="nicht erhalten"):
        validate_budget_transfer_allowed(planning_enabled=True, kinds=(INCOME, INCOME))
    with pytest.raises(ValidationError, match="Planung"):
        validate_budget_transfer_allowed(planning_enabled=False, kinds=(INCOME, STANDARD))
