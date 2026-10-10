from dataclasses import dataclass
from datetime import date

from meine_kasse.domain.enums import CostCenterKind


@dataclass(frozen=True, slots=True)
class CostCenter:
    id: str
    name: str
    number: str
    valid_from: date
    kind: CostCenterKind
    notes: str
    is_active: bool = True
