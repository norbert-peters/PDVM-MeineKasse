from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class PeriodClosure:
    """Abgeschlossener Monat mit Signatur."""

    id: str
    year: int
    month: int
    closed_on: date
    closed_by_user_id: str
    signature: str


@dataclass(frozen=True, slots=True)
class YearClosure:
    """Abgeschlossenes Jahr mit Signatur über die zwölf Monatssignaturen."""

    id: str
    year: int
    closed_on: date
    closed_by_user_id: str
    signature: str
