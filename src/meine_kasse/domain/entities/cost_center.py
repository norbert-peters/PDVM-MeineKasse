from dataclasses import dataclass
from datetime import date

from meine_kasse.domain.enums import CostCenterKind, IncomeMode


@dataclass(frozen=True, slots=True)
class CostCenter:
    """`income_mode` ist genau bei der Art `INCOME` gesetzt, sonst `None`."""

    id: str
    name: str
    number: str
    valid_from: date
    kind: CostCenterKind
    notes: str
    is_active: bool = True
    income_mode: IncomeMode | None = None
