from dataclasses import dataclass

from meine_kasse.domain.enums import FilterOperator, ReportSource


@dataclass(frozen=True, slots=True)
class ReportFilter:
    """Bedingung auf einer Spalte. `value` steht so, wie der Anwender sie eingibt."""

    column: str
    operator: FilterOperator
    value: str


@dataclass(frozen=True, slots=True)
class ReportSort:
    column: str
    ascending: bool = True


@dataclass(frozen=True, slots=True)
class ReportGroup:
    """Gruppenebene. Mit `summary_only` erscheinen nur Summen, keine Einzelzeilen darunter."""

    column: str
    summary_only: bool = False


@dataclass(frozen=True, slots=True)
class ReportDefinition:
    """Gespeicherte Auswertung eines Anwenders (Vorgabe 2.14). Spaltenreihenfolge ist wirksam."""

    name: str
    data_source: ReportSource
    columns: tuple[str, ...]
    filters: tuple[ReportFilter, ...] = ()
    sort: ReportSort | None = None
    groups: tuple[ReportGroup, ...] = ()
