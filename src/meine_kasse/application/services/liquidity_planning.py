"""Liquiditätsplanung je Planmonat (Architekturvorgabe 2.16).

Stellt je Monat die erwarteten Einnahmen der Einnahmen-Kostenstellen dem Liquiditätsbedarf der
Kostenstellen mit Plan gegenüber. Die Auswertung liest nur und schreibt nichts.
"""

from dataclasses import dataclass

from meine_kasse.application.services.income_planning import build_income_view
from meine_kasse.application.services.reserve_projection import project_cost_center
from meine_kasse.domain.enums import CostCenterKind
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.liquidity_rules import (
    LiquidityMonth,
    cumulative_balances,
    expected_income,
    uncovered_payments,
)
from meine_kasse.domain.services.planning_rules import MONTHS


@dataclass(frozen=True, slots=True)
class LiquidityView:
    year: int
    months: tuple[LiquidityMonth, ...]

    @property
    def cumulative_cents(self) -> dict[int, int]:
        return cumulative_balances(self.months)

    @property
    def income_cents(self) -> int:
        return sum(month.income_cents for month in self.months)

    @property
    def need_cents(self) -> int:
        return sum(month.need_cents for month in self.months)

    @property
    def balance_cents(self) -> int:
        return self.income_cents - self.need_cents

    @property
    def shortfall_months(self) -> tuple[int, ...]:
        """Monate, in denen die Einnahmen des Monats den Bedarf nicht decken."""
        return tuple(month.month for month in self.months if month.balance_cents < 0)


def build_liquidity_view(uow: UnitOfWork, year: int) -> LiquidityView:
    income = dict.fromkeys(MONTHS, 0)
    reserve = dict.fromkeys(MONTHS, 0)
    payment = dict.fromkeys(MONTHS, 0)
    bank_outflow = dict.fromkeys(MONTHS, 0)
    reserve_release = dict.fromkeys(MONTHS, 0)
    closed_months = uow.closures.closed_months()
    year_closed = year in uow.closures.closed_years()
    closed = {m: year_closed or (year, m) in closed_months for m in MONTHS}

    for cost_center in uow.cost_centers.list_all():
        if cost_center.kind is CostCenterKind.INCOME:
            view = build_income_view(uow, cost_center, year)
            for item in view.months:
                income[item.month] += expected_income(
                    view.mode, item.plan_cents, item.realized_cents, closed=item.is_closed
                )
        elif cost_center.kind is CostCenterKind.STANDARD:
            for reserve_year in project_cost_center(uow, cost_center.id, year):
                if reserve_year.plan.year != year:
                    continue
                uncovered = uncovered_payments(
                    reserve_year.effective_movement, reserve_year.outlook.release
                )
                for month in MONTHS:
                    reserve[month] += reserve_year.reserve_plan.get(month, 0)
                    payment[month] += uncovered[month]
                    bank_outflow[month] += reserve_year.effective_movement.get(month, 0)
                    reserve_release[month] += reserve_year.outlook.release.get(month, 0)

    return LiquidityView(
        year,
        tuple(
            LiquidityMonth(
                month,
                income[month],
                reserve[month],
                payment[month],
                closed[month],
                bank_outflow[month],
                reserve_release[month],
            )
            for month in MONTHS
        ),
    )
