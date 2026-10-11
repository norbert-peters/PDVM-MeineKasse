from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import CostCenterPlan, MonthlyActual, MonthlyPlan
from meine_kasse.domain.enums import PlanMode
from meine_kasse.infrastructure.database.models import (
    CostCenterPlanModel,
    MonthlyActualModel,
    MonthlyPlanModel,
)


def _plan_to_entity(model: CostCenterPlanModel) -> CostCenterPlan:
    return CostCenterPlan(
        id=model.id,
        cost_center_id=model.cost_center_id,
        year=model.year,
        base_budget_cents=model.base_budget_cents,
        budget_transfer_cents=model.budget_transfer_cents,
        reserve_carry_in_cents=model.reserve_carry_in_cents,
        reserve_carry_out_cents=model.reserve_carry_out_cents,
    )


def _monthly_to_entity(model: MonthlyPlanModel) -> MonthlyPlan:
    return MonthlyPlan(
        id=model.id,
        cost_center_plan_id=model.cost_center_plan_id,
        month=model.month,
        plan_cents=model.plan_cents,
        reserve_plan_cents=model.reserve_plan_cents,
        plan_mode=PlanMode(model.plan_mode),
    )


def _actual_to_entity(model: MonthlyActualModel) -> MonthlyActual:
    return MonthlyActual(
        id=model.id,
        cost_center_id=model.cost_center_id,
        year=model.year,
        month=model.month,
        debit_cents=model.debit_cents,
        credit_cents=model.credit_cents,
        reserve_actual_cents=model.reserve_actual_cents,
    )


class SqlPlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_plan(self, cost_center_id: str, year: int) -> CostCenterPlan | None:
        statement = select(CostCenterPlanModel).where(
            CostCenterPlanModel.cost_center_id == cost_center_id, CostCenterPlanModel.year == year
        )
        model = self._session.scalars(statement).first()
        return None if model is None else _plan_to_entity(model)

    def save_plan(self, plan: CostCenterPlan) -> None:
        model = self._session.get(CostCenterPlanModel, plan.id)
        if model is None:
            model = CostCenterPlanModel(id=plan.id, cost_center_id=plan.cost_center_id)
            self._session.add(model)
        model.year = plan.year
        model.base_budget_cents = plan.base_budget_cents
        model.budget_transfer_cents = plan.budget_transfer_cents
        model.reserve_carry_in_cents = plan.reserve_carry_in_cents
        model.reserve_carry_out_cents = plan.reserve_carry_out_cents
        self._session.flush()

    def list_plans(self) -> Sequence[CostCenterPlan]:
        return [
            _plan_to_entity(model) for model in self._session.scalars(select(CostCenterPlanModel))
        ]

    def monthly_plans(self, cost_center_id: str, year: int) -> Sequence[MonthlyPlan]:
        statement = (
            select(MonthlyPlanModel)
            .join(
                CostCenterPlanModel, CostCenterPlanModel.id == MonthlyPlanModel.cost_center_plan_id
            )
            .where(
                CostCenterPlanModel.cost_center_id == cost_center_id,
                CostCenterPlanModel.year == year,
            )
            .order_by(MonthlyPlanModel.month)
        )
        return [_monthly_to_entity(model) for model in self._session.scalars(statement)]

    def monthly_plans_for_month(self, year: int, month: int) -> Sequence[tuple[str, MonthlyPlan]]:
        statement = (
            select(CostCenterPlanModel.cost_center_id, MonthlyPlanModel)
            .join(
                CostCenterPlanModel, CostCenterPlanModel.id == MonthlyPlanModel.cost_center_plan_id
            )
            .where(CostCenterPlanModel.year == year, MonthlyPlanModel.month == month)
        )
        return [
            (cost_center_id, _monthly_to_entity(model))
            for cost_center_id, model in self._session.execute(statement)
        ]

    def save_monthly_plan(self, plan: MonthlyPlan) -> None:
        model = self._session.get(MonthlyPlanModel, plan.id)
        if model is None:
            model = MonthlyPlanModel(id=plan.id, cost_center_plan_id=plan.cost_center_plan_id)
            self._session.add(model)
        model.month = plan.month
        model.plan_cents = plan.plan_cents
        model.reserve_plan_cents = plan.reserve_plan_cents
        model.plan_mode = plan.plan_mode.value
        self._session.flush()

    def get_actual(self, cost_center_id: str, year: int, month: int) -> MonthlyActual | None:
        statement = select(MonthlyActualModel).where(
            MonthlyActualModel.cost_center_id == cost_center_id,
            MonthlyActualModel.year == year,
            MonthlyActualModel.month == month,
        )
        model = self._session.scalars(statement).first()
        return None if model is None else _actual_to_entity(model)

    def save_actual(self, actual: MonthlyActual) -> None:
        model = self._session.get(MonthlyActualModel, actual.id)
        if model is None:
            model = MonthlyActualModel(id=actual.id, cost_center_id=actual.cost_center_id)
            self._session.add(model)
        model.year = actual.year
        model.month = actual.month
        model.debit_cents = actual.debit_cents
        model.credit_cents = actual.credit_cents
        model.reserve_actual_cents = actual.reserve_actual_cents
        self._session.flush()

    def actuals_for_year(self, cost_center_id: str, year: int) -> Sequence[MonthlyActual]:
        statement = (
            select(MonthlyActualModel)
            .where(
                MonthlyActualModel.cost_center_id == cost_center_id, MonthlyActualModel.year == year
            )
            .order_by(MonthlyActualModel.month)
        )
        return [_actual_to_entity(model) for model in self._session.scalars(statement)]

    def list_actuals(self) -> Sequence[MonthlyActual]:
        return [
            _actual_to_entity(model) for model in self._session.scalars(select(MonthlyActualModel))
        ]

    def delete_actual(self, actual_id: str) -> None:
        self._session.execute(delete(MonthlyActualModel).where(MonthlyActualModel.id == actual_id))
        self._session.flush()
