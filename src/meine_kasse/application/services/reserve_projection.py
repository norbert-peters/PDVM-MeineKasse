"""Fortschreibung der Rückstellungen aus Plan und Ist (Architekturvorgabe 2.12).

Die Entlastung je Monat (`reserve_actual_cents`) und der Vortrag (`reserve_carry_*_cents`) sind
Projektionen. Sie werden aus Zuführungen und Ist-Bewegung berechnet und sind jederzeit neu
aufbaubar. Der Vortrag eines Jahres ist der Endbestand des Vorjahres, sofern die Kostenstelle
dort einen Plan hat. Sonst ist er manuell erfasst.
"""

from dataclasses import dataclass, replace

from meine_kasse.domain.entities import CostCenterPlan
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.planning_rules import MONTHS
from meine_kasse.domain.services.reserve_rules import (
    ReserveYear,
    compute_reserve_year,
    effective_movement,
)


@dataclass(frozen=True, slots=True)
class YearReserve:
    """`result` rechnet nur mit der Ist-Bewegung, `outlook` zusätzlich mit offenen Planzahlungen."""

    plan: CostCenterPlan
    carry_in_cents: int
    carry_in_derived: bool
    reserve_plan_total_cents: int
    result: ReserveYear
    outlook: ReserveYear
    reserve_plan: dict[int, int]
    effective_movement: dict[int, int]

    @property
    def has_reserve(self) -> bool:
        """Die Kostenstelle hat im Jahr eine Rückstellung (Vortrag oder Zuführung)."""
        return self.carry_in_cents > 0 or self.reserve_plan_total_cents > 0


def project_cost_center(uow: UnitOfWork, cost_center_id: str, from_year: int) -> list[YearReserve]:
    """Berechnet die Rückstellungen aller Planjahre ab `from_year` (ohne zu speichern)."""
    plans = list(uow.plans.plans_of_cost_center(cost_center_id))
    known_years = {plan.year for plan in plans}
    closed_months = uow.closures.closed_months()
    closed_years = uow.closures.closed_years()
    carry_out: dict[int, int] = {}
    results: list[YearReserve] = []
    for plan in plans:
        if plan.year < from_year:
            carry_out[plan.year] = plan.reserve_carry_out_cents
            continue
        derived = plan.year - 1 in known_years
        carry_in = carry_out[plan.year - 1] if derived else plan.reserve_carry_in_cents
        monthly = uow.plans.monthly_plans(cost_center_id, plan.year)
        reserve_plan = {item.month: item.reserve_plan_cents for item in monthly}
        plan_cents = {item.month: item.plan_cents for item in monthly}
        movement = {
            actual.month: actual.movement_cents
            for actual in uow.plans.actuals_for_year(cost_center_id, plan.year)
        }
        closed = (
            set(MONTHS)
            if plan.year in closed_years
            else {month for month in MONTHS if (plan.year, month) in closed_months}
        )
        result = compute_reserve_year(carry_in, reserve_plan, movement)
        effective = effective_movement(plan_cents, movement, closed)
        outlook = compute_reserve_year(carry_in, reserve_plan, effective)
        carry_out[plan.year] = outlook.carry_out_cents
        results.append(
            YearReserve(
                plan,
                carry_in,
                derived,
                sum(reserve_plan.values()),
                result,
                outlook,
                reserve_plan,
                effective,
            )
        )
    return results


def apply_projection(uow: UnitOfWork, cost_center_id: str, from_year: int) -> bool:
    """Schreibt Entlastung und Vorträge ab `from_year` fort. Gibt zurück, ob sich etwas änderte."""
    changed = False
    for item in project_cost_center(uow, cost_center_id, from_year):
        for actual in uow.plans.actuals_for_year(cost_center_id, item.plan.year):
            release = item.result.release[actual.month]
            if actual.reserve_actual_cents != release:
                uow.plans.save_actual(replace(actual, reserve_actual_cents=release))
                changed = True
        plan = item.plan
        if (
            plan.reserve_carry_in_cents != item.carry_in_cents
            or plan.reserve_carry_out_cents != item.outlook.carry_out_cents
        ):
            uow.plans.save_plan(
                replace(
                    plan,
                    reserve_carry_in_cents=item.carry_in_cents,
                    reserve_carry_out_cents=item.outlook.carry_out_cents,
                )
            )
            changed = True
    return changed


def projection_mismatch_cost_centers(uow: UnitOfWork, year: int) -> list[str]:
    """Kostenstellen, deren gespeicherte Rückstellung im Jahr nicht der Berechnung entspricht."""
    mismatched: list[str] = []
    for cost_center_id in sorted({plan.cost_center_id for plan in uow.plans.list_plans()}):
        for item in project_cost_center(uow, cost_center_id, 0):
            if item.plan.year != year:
                continue
            stored = {
                actual.month: actual.reserve_actual_cents
                for actual in uow.plans.actuals_for_year(cost_center_id, year)
            }
            expected_release = {m: c for m, c in item.result.release.items() if c}
            stored_release = {m: c for m, c in stored.items() if c}
            if (
                expected_release != stored_release
                or item.plan.reserve_carry_in_cents != item.carry_in_cents
                or item.plan.reserve_carry_out_cents != item.outlook.carry_out_cents
            ):
                mismatched.append(cost_center_id)
    return mismatched
