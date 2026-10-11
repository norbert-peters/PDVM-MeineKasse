from dataclasses import dataclass
from datetime import date

from meine_kasse.domain.enums import ClosureKind


@dataclass(frozen=True, slots=True)
class ClosureReopening:
    """Dauerhafter Nachweis über das Wiedereröffnen eines Abschlusses.

    Der Eintrag bleibt bestehen, auch wenn der Zeitraum später erneut abgeschlossen wird.
    """

    id: str
    kind: ClosureKind
    year: int
    month: int | None
    reopened_on: date
    reopened_by_user_id: str
    reason: str
    previous_signature: str
    previous_closed_on: date
    previous_closed_by_user_id: str
    signature_was_valid: bool


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
