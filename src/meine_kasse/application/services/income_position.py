"""Stand einer Einnahmen-Kostenstelle im Jahr aus Plan und Ist (Architekturvorgabe 2.15)."""

from meine_kasse.domain.entities import CostCenter
from meine_kasse.domain.enums import IncomeMode
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.income_rules import IncomePosition, passed_on_cents


def income_position(uow: UnitOfWork, cost_center: CostCenter, year: int) -> IncomePosition:
    """Plan, gebuchte Einnahme (Haben − Soll) und weitergegebener Betrag der Einnahmenstelle."""
    plan = uow.plans.get_plan(cost_center.id, year)
    planned = sum(item.plan_cents for item in uow.plans.monthly_plans(cost_center.id, year))
    actuals = uow.plans.actuals_for_year(cost_center.id, year)
    realized = -sum(item.movement_cents for item in actuals)
    return IncomePosition(
        mode=cost_center.income_mode or IncomeMode.PLAN,
        planned_cents=planned,
        realized_cents=realized,
        passed_on_cents=passed_on_cents(plan.budget_transfer_cents if plan else 0),
    )
