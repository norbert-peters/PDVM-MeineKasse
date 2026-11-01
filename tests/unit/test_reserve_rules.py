import random

import pytest

from meine_kasse.domain.services.reserve_rules import (
    compute_reserve_outlook,
    compute_reserve_year,
    distribute_reserve,
    is_directly_planned,
    plan_balances,
    plan_shortfalls,
)

ALL = list(range(1, 13))


def _plan(**cents: int) -> dict[int, int]:
    return {int(key[1:]): value for key, value in cents.items()}


def _distribute(
    budget: int,
    plan: dict[int, int],
    *,
    carry_in: int = 0,
    fixed: dict[int, int] | None = None,
    free: list[int] | None = None,
    to_payment_targets: bool = True,
) -> dict[int, int]:
    return distribute_reserve(
        budget_cents=budget,
        carry_in_cents=carry_in,
        plan_cents=plan,
        fixed=fixed or {},
        free_months=ALL if free is None else free,
        to_payment_targets=to_payment_targets,
    )


# Direkte Planung


def test_planning_in_all_months_means_no_reserve() -> None:
    plan = dict.fromkeys(ALL, 100)

    assert is_directly_planned(plan)
    assert _distribute(1200, plan) == dict.fromkeys(ALL, 0)
    assert plan_shortfalls(0, dict.fromkeys(ALL, 0), plan) == {}


def test_a_missing_month_is_enough_for_reserves() -> None:
    plan = dict.fromkeys(range(1, 12), 100)

    assert not is_directly_planned(plan)
    assert not is_directly_planned({})


# Maschinelle Verteilung


def test_without_planned_payments_the_budget_is_spread_evenly() -> None:
    result = _distribute(1200, {})

    assert result == dict.fromkeys(ALL, 100)


def test_even_spread_gives_the_rounding_rest_to_the_first_months() -> None:
    result = _distribute(1000, {})

    assert sum(result.values()) == 1000
    assert result[1] == 84 and result[12] == 83


def test_planned_payments_do_not_change_the_even_spread() -> None:
    plan = _plan(m1=1200)

    result = _distribute(1200, plan, to_payment_targets=False)

    assert result == dict.fromkeys(ALL, 100)
    assert plan_shortfalls(0, result, plan) == {1: 1100}


def test_even_spread_still_stops_when_all_months_are_planned() -> None:
    result = _distribute(1200, dict.fromkeys(ALL, 100), to_payment_targets=False)

    assert result == dict.fromkeys(ALL, 0)


def test_reserve_is_raised_before_a_payment_that_is_not_covered() -> None:
    plan = _plan(m3=600, m9=600)

    result = _distribute(1200, plan)

    assert sum(result.values()) == 1200
    assert [result[m] for m in (1, 2, 3)] == [200, 200, 200]
    assert [result[m] for m in range(4, 10)] == [100] * 6
    assert [result[m] for m in (10, 11, 12)] == [0, 0, 0]
    assert plan_shortfalls(0, result, plan) == {}


def test_payment_in_december_needs_no_shifting() -> None:
    result = _distribute(1200, _plan(m12=1200))

    assert result == dict.fromkeys(ALL, 100)


def test_payment_in_january_pulls_the_whole_amount_forward() -> None:
    plan = _plan(m1=1200)

    result = _distribute(1200, plan)

    assert result[1] == 1200
    assert sum(result.values()) == 1200
    assert plan_shortfalls(0, result, plan) == {}


def test_carry_in_reduces_the_amount_that_has_to_be_reserved_early() -> None:
    plan = _plan(m3=600)

    without = _distribute(1200, plan)
    with_carry = _distribute(1200, plan, carry_in=300)

    assert sum(without[m] for m in (1, 2, 3)) == 600
    assert sum(with_carry[m] for m in (1, 2, 3)) == 300  # 3 x 100 genügen mit Vortrag 300
    assert plan_shortfalls(300, with_carry, plan) == {}


def test_manual_and_closed_months_are_never_changed() -> None:
    plan = _plan(m6=600)
    fixed = {1: 50, 2: 70}

    result = _distribute(1200, plan, fixed=fixed, free=list(range(3, 13)))

    assert result[1] == 50 and result[2] == 70
    assert sum(result.values()) == 1200
    assert plan_shortfalls(0, result, plan) == {}


def test_budget_already_bound_by_fixed_months_is_not_distributed_twice() -> None:
    result = _distribute(1000, {}, fixed={1: 400, 2: 600}, free=list(range(3, 13)))

    assert sum(result.values()) == 1000
    assert all(result[m] == 0 for m in range(3, 13))


def test_without_free_months_nothing_is_calculated() -> None:
    result = _distribute(1200, _plan(m3=600), fixed={1: 10}, free=[])

    assert result[1] == 10 and sum(result.values()) == 10


def test_shortfall_is_reported_when_the_reserve_cannot_be_raised() -> None:
    plan = _plan(m2=600)

    # Der Ansatz ist durch den gesperrten März gebunden, für Februar bleibt nichts.
    result = _distribute(600, plan, fixed={1: 0, 3: 600}, free=[2, 4])

    assert plan_shortfalls(0, result, plan) == {2: 600}


def test_budget_smaller_than_planned_payments_is_reported_as_shortfall() -> None:
    plan = _plan(m1=500, m2=500)

    result = _distribute(600, plan)

    assert sum(result.values()) == 600
    assert sum(plan_shortfalls(0, result, plan).values()) == 400
    assert set(plan_shortfalls(0, result, plan)) <= {1, 2}


def test_a_shortfall_is_reported_once_in_the_month_it_arises() -> None:
    assert plan_shortfalls(0, {}, {3: 100}) == {3: 100}
    assert plan_shortfalls(0, {1: 50}, {3: 100, 4: 20}) == {3: 50, 4: 20}


def test_balances_are_cumulative() -> None:
    balances = plan_balances(100, {1: 50, 2: 50}, {2: 120})

    assert balances[1] == 150 and balances[2] == 80 and balances[12] == 80


@pytest.mark.parametrize("seed", range(40))
def test_distribution_invariants_hold_for_random_plans(seed: int) -> None:
    rng = random.Random(seed)
    budget = rng.randrange(0, 5000) * 10
    carry = rng.choice([0, 0, rng.randrange(0, 500)])
    plan: dict[int, int] = {}
    remaining = budget
    for month in rng.sample(ALL, rng.randrange(0, 9)):
        amount = min(remaining, rng.randrange(0, 800))
        plan[month] = amount
        remaining -= amount
    fixed = {m: rng.randrange(0, 50) for m in rng.sample(ALL, rng.randrange(0, 3))}
    free = [m for m in ALL if m not in fixed]

    result = _distribute(budget, plan, carry_in=carry, fixed=fixed, free=free)

    assert all(value >= 0 for value in result.values())
    assert all(result[m] == value for m, value in fixed.items())
    if not is_directly_planned(plan):
        assert sum(result.values()) <= max(budget, sum(fixed.values()))
    # Wiederholung ergibt dasselbe Ergebnis (deterministisch)
    assert result == _distribute(budget, plan, carry_in=carry, fixed=fixed, free=free)
    if sum(plan.values()) <= budget and not fixed and carry == 0:
        assert plan_shortfalls(carry, result, plan) == {}


# Entlastung durch Ist


def test_release_is_limited_to_the_available_reserve_and_reports_the_rest() -> None:
    reserve = dict.fromkeys(ALL, 100)

    year = compute_reserve_year(0, reserve, {1: 250})

    assert year.release[1] == 100
    assert year.shortfall == {1: 150}
    assert year.balance[1] == 0
    assert year.balance[2] == 100


def test_release_includes_the_current_month_and_the_carry_in() -> None:
    year = compute_reserve_year(300, {1: 100}, {1: 350})

    assert year.release[1] == 350 and year.shortfall == {}
    assert year.balance[1] == 50


def test_later_months_see_earlier_releases() -> None:
    reserve = dict.fromkeys(ALL, 100)

    year = compute_reserve_year(0, reserve, {1: 100, 2: 150, 3: 50})

    assert [year.release[m] for m in (1, 2, 3)] == [100, 100, 50]
    assert year.shortfall == {2: 50}
    assert year.balance[3] == 50


def test_refund_returns_at_most_the_earlier_release() -> None:
    reserve = dict.fromkeys(ALL, 100)

    year = compute_reserve_year(0, reserve, {1: 100, 2: -300})

    assert year.release[2] == -100
    assert year.balance[2] == 200
    assert all(balance >= 0 for balance in year.balance.values())


def test_refund_without_earlier_release_changes_nothing() -> None:
    year = compute_reserve_year(0, {1: 100}, {1: -50})

    assert year.release[1] == 0 and year.balance[1] == 100


def test_unplanned_spending_without_reserve_is_a_full_shortfall_but_not_negative() -> None:
    year = compute_reserve_year(0, {}, {5: 400})

    assert year.release[5] == 0 and year.shortfall == {5: 400}
    assert year.carry_out_cents == 0


def test_unused_reserve_is_carried_out() -> None:
    reserve = dict.fromkeys(ALL, 100)

    year = compute_reserve_year(50, reserve, {4: 300})

    assert year.carry_out_cents == 50 + 1200 - 300


@pytest.mark.parametrize("seed", range(30))
def test_balance_is_never_negative_and_ignores_booking_order(seed: int) -> None:
    rng = random.Random(seed)
    reserve = {m: rng.randrange(0, 300) for m in ALL}
    movement = {m: rng.randrange(-400, 600) for m in rng.sample(ALL, rng.randrange(0, 12))}
    carry = rng.randrange(0, 200)

    year = compute_reserve_year(carry, reserve, movement)

    assert all(balance >= 0 for balance in year.balance.values())
    assert year.carry_out_cents == carry + sum(reserve.values()) - sum(year.release.values())
    shuffled = dict(sorted(movement.items(), reverse=True))
    assert compute_reserve_year(carry, reserve, shuffled) == year


# Ausblick nach Plan


def test_planned_payments_relieve_the_reserve_in_open_months() -> None:
    reserve = dict.fromkeys(ALL, 100)

    year = compute_reserve_outlook(0, reserve, _plan(m6=600, m12=600), {}, set())

    assert year.release[6] == 600 and year.release[12] == 600
    assert year.balance[6] == 0 and year.carry_out_cents == 0


def test_the_actual_payment_replaces_the_plan_in_a_closed_month() -> None:
    reserve = dict.fromkeys(ALL, 100)

    year = compute_reserve_outlook(0, reserve, _plan(m6=600), {6: 450}, {6})

    assert year.release[6] == 450
    assert year.carry_out_cents == 1200 - 450


def test_an_open_month_uses_the_higher_of_plan_and_actual() -> None:
    reserve = dict.fromkeys(ALL, 100)

    partial = compute_reserve_outlook(0, reserve, _plan(m6=600), {6: 200}, set())
    exceeded = compute_reserve_outlook(0, reserve, _plan(m6=300), {6: 400}, set())

    assert partial.release[6] == 600
    assert exceeded.release[6] == 400


def test_outlook_without_plan_equals_the_actual_calculation() -> None:
    reserve = dict.fromkeys(ALL, 100)
    movement = {3: 250, 7: 100}

    assert compute_reserve_outlook(40, reserve, {}, movement, set()) == compute_reserve_year(
        40, reserve, movement
    )


def test_a_planned_payment_is_limited_to_the_saved_amount() -> None:
    year = compute_reserve_outlook(0, dict.fromkeys(ALL, 100), _plan(m2=500), {}, set())

    assert year.release[2] == 200
    assert year.shortfall == {2: 300}
