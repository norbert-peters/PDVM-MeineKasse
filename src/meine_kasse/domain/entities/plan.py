from dataclasses import dataclass

from meine_kasse.domain.enums import PlanMode


@dataclass(frozen=True, slots=True)
class CostCenterPlan:
    """Jahresplan. Der wirksame Ansatz ist Basisansatz + Ansatzumbuchungen."""

    id: str
    cost_center_id: str
    year: int
    base_budget_cents: int = 0
    budget_transfer_cents: int = 0
    reserve_carry_in_cents: int = 0
    reserve_carry_out_cents: int = 0

    @property
    def effective_budget_cents(self) -> int:
        return self.base_budget_cents + self.budget_transfer_cents


@dataclass(frozen=True, slots=True)
class MonthlyPlan:
    id: str
    cost_center_plan_id: str
    month: int
    plan_cents: int
    reserve_plan_cents: int
    plan_mode: PlanMode


@dataclass(frozen=True, slots=True)
class MonthlyActual:
    """Projektion der Ist-Buchungen. Soll und Haben sind getrennt und vorzeichenbehaftet."""

    id: str
    cost_center_id: str
    year: int
    month: int
    debit_cents: int = 0
    credit_cents: int = 0
    reserve_actual_cents: int = 0

    @property
    def movement_cents(self) -> int:
        """Ist-Bewegung = Soll - Haben."""
        return self.debit_cents - self.credit_cents
