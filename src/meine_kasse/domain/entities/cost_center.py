from dataclasses import dataclass
from datetime import date

from meine_kasse.domain.enums import CostCenterKind, IncomeMode


@dataclass(frozen=True, slots=True)
class CostCenter:
    """`income_mode` ist genau bei der Art `INCOME` gesetzt, sonst `None`.

    `always_in_plan_report`: Die Kostenstelle erscheint in der Plan/Ist-Auswertung auch ohne Plan
    und ohne Ist-Buchung, im aktuellen und im nächsten Planjahr (nur bei `STANDARD` und
    `WITHOUT_PLAN`).
    """

    id: str
    name: str
    number: str
    valid_from: date
    kind: CostCenterKind
    notes: str
    is_active: bool = True
    income_mode: IncomeMode | None = None
    always_in_plan_report: bool = False
