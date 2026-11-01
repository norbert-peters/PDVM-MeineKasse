"""Liquiditätsplanung je Monat (Architekturvorgabe 2.16)."""

from datetime import date

from conftest import World
from meine_kasse.application.services.income_planning import IncomeMonthInput
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.application.services.planning_service import MonthPlanInput, PlanningService
from meine_kasse.domain.enums import CostCenterKind, IncomeMode
from meine_kasse.domain.services.liquidity_rules import (
    LiquidityMonth,
    cumulative_balances,
    expected_income,
    uncovered_payments,
)

YEAR = 2026


def _income(master_data: MasterDataService, mode: IncomeMode, number: str = "900") -> str:
    return master_data.create_cost_center(
        number=number,
        name=f"Einnahme {number}",
        valid_from=date(2026, 1, 1),
        kind=CostCenterKind.INCOME,
        income_mode=mode,
    )


def _plan_income(planning: PlanningService, world: World, cost_center: str, cents: int) -> None:
    planning.save_income_plan(
        cost_center,
        YEAR,
        months=[IncomeMonthInput(month, cents) for month in range(1, 13)],
        actor_id=world.actor,
    )


def test_open_months_use_plan_but_at_least_the_actual_income() -> None:
    assert expected_income(IncomeMode.PLAN, 1000, 0, closed=False) == 1000
    assert expected_income(IncomeMode.PLAN, 1000, 1500, closed=False) == 1500


def test_closed_months_and_uncertain_income_count_only_actual_income() -> None:
    assert expected_income(IncomeMode.PLAN, 1000, 400, closed=True) == 400
    assert expected_income(IncomeMode.ACTUAL, 1000, 0, closed=False) == 0
    assert expected_income(IncomeMode.ACTUAL, 1000, 250, closed=False) == 250
    assert expected_income(IncomeMode.PLAN, 1000, -50, closed=False) == 1000


def test_payments_covered_by_the_reserve_do_not_burden_the_liquidity_again() -> None:
    assert uncovered_payments({3: 600, 4: 100}, {3: 600, 4: 40}) == {
        **dict.fromkeys(range(1, 13), 0),
        4: 60,
    }
    assert uncovered_payments({1: -50}, {1: -50})[1] == 0


def test_cumulative_balance_adds_up_over_the_months() -> None:
    months = [
        LiquidityMonth(1, 1000, 600, 0, False),
        LiquidityMonth(2, 1000, 600, 900, False),
        LiquidityMonth(3, 1000, 600, 0, False),
    ]

    assert [m.balance_cents for m in months] == [400, -500, 400]
    assert cumulative_balances(months) == {1: 400, 2: -100, 3: 300}


def test_reserve_months_compare_income_with_the_contributions(
    planning: PlanningService, master_data: MasterDataService, world: World
) -> None:
    planning.save_plan(world.cc_a, YEAR, base_budget_cents=120000, months=[], actor_id=world.actor)
    _plan_income(planning, world, _income(master_data, IncomeMode.PLAN), 15000)

    view = planning.get_liquidity_view(YEAR)

    assert all(m.income_cents == 15000 and m.reserve_cents == 10000 for m in view.months)
    assert all(m.payment_cents == 0 and m.balance_cents == 5000 for m in view.months)
    assert view.shortfall_months == ()
    assert view.cumulative_cents[12] == 60000 == view.balance_cents


def test_planned_payment_is_covered_by_the_reserve_and_counted_once(
    planning: PlanningService, master_data: MasterDataService, world: World
) -> None:
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=120000,
        months=[MonthPlanInput(12, 120000)],
        actor_id=world.actor,
    )

    view = planning.get_liquidity_view(YEAR)

    assert [m.need_cents for m in view.months] == [10000] * 12
    assert view.need_cents == 120000


def test_monthly_payments_without_reserve_burden_the_month_directly(
    planning: PlanningService, master_data: MasterDataService, world: World
) -> None:
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=120000,
        months=[MonthPlanInput(month, 10000) for month in range(1, 13)],
        actor_id=world.actor,
    )
    _plan_income(planning, world, _income(master_data, IncomeMode.PLAN), 8000)

    view = planning.get_liquidity_view(YEAR)

    assert all(m.reserve_cents == 0 and m.payment_cents == 10000 for m in view.months)
    assert view.shortfall_months == tuple(range(1, 13))
    assert view.cumulative_cents[12] == -24000


def test_a_payment_beyond_the_reserve_hits_the_liquidity_in_its_month(
    planning: PlanningService, master_data: MasterDataService, world: World
) -> None:
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=120000,
        months=[MonthPlanInput(2, 50000)],
        actor_id=world.actor,
    )

    view = planning.get_liquidity_view(YEAR)

    assert view.months[1].payment_cents == 30000
    assert view.months[1].need_cents == 40000
    assert view.months[0].payment_cents == 0


def test_without_any_plan_the_overview_is_empty(planning: PlanningService) -> None:
    view = planning.get_liquidity_view(YEAR)

    assert view.income_cents == 0 and view.need_cents == 0 and view.shortfall_months == ()


def test_uncertain_income_without_actuals_does_not_count(
    planning: PlanningService, master_data: MasterDataService, world: World
) -> None:
    _plan_income(planning, world, _income(master_data, IncomeMode.ACTUAL, "910"), 9000)

    assert planning.get_liquidity_view(YEAR).income_cents == 0
