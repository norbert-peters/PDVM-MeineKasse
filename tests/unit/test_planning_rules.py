import pytest

from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.services.planning_rules import (
    check_distribution,
    check_reserve_distribution,
    distribute_evenly,
    validate_month_amounts,
    validate_plan_amounts,
)


def test_even_distribution_sums_exactly_and_gives_remainder_to_first_months() -> None:
    result = distribute_evenly(1000, [1, 2, 3])
    assert result == {1: 334, 2: 333, 3: 333}
    assert sum(result.values()) == 1000


def test_even_distribution_over_twelve_months() -> None:
    result = distribute_evenly(120000, list(range(1, 13)))
    assert set(result.values()) == {10000}
    assert sum(distribute_evenly(100001, list(range(1, 13))).values()) == 100001


def test_even_distribution_rejects_negative_total_and_empty_months() -> None:
    with pytest.raises(ValidationError):
        distribute_evenly(-1, [1])
    with pytest.raises(ValidationError):
        distribute_evenly(100, [])


def test_distribution_may_use_the_whole_budget_but_not_more() -> None:
    check_distribution(10000, 10000)
    check_distribution(10000, 0)
    with pytest.raises(ValidationError, match="1,00 €"):
        check_distribution(10000, 10100)
    with pytest.raises(ValidationError, match="negativ"):
        check_distribution(-1, 0)


def test_reserve_total_may_not_exceed_the_budget() -> None:
    check_reserve_distribution(10000, 10000)
    with pytest.raises(ValidationError, match="Rückstellungen.*1,00 €"):
        check_reserve_distribution(10000, 10100)


def test_amount_validation() -> None:
    validate_plan_amounts(base_cents=0, carry_in_cents=0)
    with pytest.raises(ValidationError):
        validate_plan_amounts(base_cents=-1, carry_in_cents=0)
    with pytest.raises(ValidationError):
        validate_plan_amounts(base_cents=0, carry_in_cents=-1)
    validate_month_amounts(1, 0, 0)
    validate_month_amounts(1, 0, None)
    with pytest.raises(ValidationError):
        validate_month_amounts(13, 0, 0)
    with pytest.raises(ValidationError):
        validate_month_amounts(1, -5, 0)
    with pytest.raises(ValidationError):
        validate_month_amounts(1, 0, -5)
