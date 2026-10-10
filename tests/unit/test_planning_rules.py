import pytest

from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.services.planning_rules import (
    check_distribution,
    distribute_evenly,
    distribute_quarters,
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


def test_quarter_distribution_uses_only_open_months() -> None:
    result = distribute_quarters({1: 3000, 2: 1000}, open_months={2, 3, 4, 5, 6})
    assert result == {2: 1500, 3: 1500, 4: 334, 5: 333, 6: 333}


def test_quarter_without_open_months_is_only_valid_for_zero() -> None:
    assert distribute_quarters({1: 0}, open_months={4, 5}) == {}
    with pytest.raises(ValidationError, match="Quartal 1"):
        distribute_quarters({1: 100}, open_months={4, 5})


def test_distribution_may_use_the_whole_budget_but_not_more() -> None:
    check_distribution(10000, 10000)
    check_distribution(10000, 0)
    with pytest.raises(ValidationError, match="1,00 €"):
        check_distribution(10000, 10100)
    with pytest.raises(ValidationError, match="negativ"):
        check_distribution(-1, 0)


def test_amount_validation() -> None:
    validate_plan_amounts(base_cents=0, carry_in_cents=0, carry_out_cents=0)
    with pytest.raises(ValidationError):
        validate_plan_amounts(base_cents=-1, carry_in_cents=0, carry_out_cents=0)
    with pytest.raises(ValidationError):
        validate_plan_amounts(base_cents=0, carry_in_cents=-1, carry_out_cents=0)
    validate_month_amounts(1, 0, 0)
    with pytest.raises(ValidationError):
        validate_month_amounts(13, 0, 0)
    with pytest.raises(ValidationError):
        validate_month_amounts(1, -5, 0)
