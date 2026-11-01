"""Datenquellen und Spaltenkatalog der allgemeinen Auswertung (Architekturvorgabe 2.14).

Es gibt eine Auswertung über Datenquellen mit einem erweiterbaren Spaltenkatalog. Eine neue
Spalte ist eine Zeile im Katalog und ein Wert in den Quellzeilen, kein neuer Bericht.
"""

from dataclasses import dataclass
from enum import StrEnum

from meine_kasse.domain.enums import FilterOperator, ReportSource


class ColumnKind(StrEnum):
    TEXT = "TEXT"
    DATE = "DATE"
    MONEY = "MONEY"
    INT = "INT"


class Summation(StrEnum):
    """`ADDITIVE`: summierbar (Soll, Haben, Plan). `NON_ADDITIVE`: Bestands- und Jahreswerte."""

    ADDITIVE = "ADDITIVE"
    NON_ADDITIVE = "NON_ADDITIVE"


@dataclass(frozen=True, slots=True)
class ColumnDef:
    key: str
    label: str
    kind: ColumnKind
    summation: Summation = Summation.NON_ADDITIVE
    groupable: bool = False

    @property
    def is_additive(self) -> bool:
        return self.summation is Summation.ADDITIVE

    @property
    def operators(self) -> tuple[FilterOperator, ...]:
        return TEXT_OPERATORS if self.kind is ColumnKind.TEXT else COMPARISON_OPERATORS


@dataclass(frozen=True, slots=True)
class SourceDef:
    source: ReportSource
    label: str
    row_meaning: str
    columns: tuple[ColumnDef, ...]

    def column(self, key: str) -> ColumnDef | None:
        return next((column for column in self.columns if column.key == key), None)


TEXT_OPERATORS = (FilterOperator.CONTAINS, FilterOperator.EQUALS, FilterOperator.NOT_EQUALS)
COMPARISON_OPERATORS = (
    FilterOperator.EQUALS,
    FilterOperator.NOT_EQUALS,
    FilterOperator.GREATER,
    FilterOperator.GREATER_OR_EQUAL,
    FilterOperator.LESS,
    FilterOperator.LESS_OR_EQUAL,
)

OPERATOR_LABELS = {
    FilterOperator.CONTAINS: "enthält",
    FilterOperator.EQUALS: "ist gleich",
    FilterOperator.NOT_EQUALS: "ist ungleich",
    FilterOperator.GREATER: "größer als",
    FilterOperator.GREATER_OR_EQUAL: "größer oder gleich",
    FilterOperator.LESS: "kleiner als",
    FilterOperator.LESS_OR_EQUAL: "kleiner oder gleich",
}

MAX_GROUP_LEVELS = 3

_TEXT = ColumnKind.TEXT
_DATE = ColumnKind.DATE
_MONEY = ColumnKind.MONEY
_INT = ColumnKind.INT
_ADD = Summation.ADDITIVE

BOOKINGS = SourceDef(
    ReportSource.BOOKINGS,
    "Buchungen",
    "Eine Zeile je Buchung",
    (
        ColumnDef("booking_date", "Buchungsdatum", _DATE, groupable=True),
        ColumnDef("origin_date", "Entstehungsdatum", _DATE, groupable=True),
        ColumnDef("fiscal_year", "Buchungsjahr", _INT, groupable=True),
        ColumnDef("fiscal_month", "Buchungsmonat", _INT, groupable=True),
        ColumnDef("cost_center", "Kostenstelle", _TEXT, groupable=True),
        ColumnDef("account", "Konto", _TEXT, groupable=True),
        ColumnDef("counter_account", "Gegenkonto", _TEXT, groupable=True),
        ColumnDef("counter_cost_center", "Gegenkostenstelle", _TEXT, groupable=True),
        ColumnDef("booking_type", "Buchungsart", _TEXT, groupable=True),
        ColumnDef("debit", "Soll", _MONEY, _ADD),
        ColumnDef("credit", "Haben", _MONEY, _ADD),
        ColumnDef("booking_text", "Buchungstext", _TEXT),
        ColumnDef("merchant", "Händler", _TEXT, groupable=True),
        ColumnDef("status", "Status", _TEXT, groupable=True),
        ColumnDef("user", "Anwender", _TEXT, groupable=True),
    ),
)

PLAN_ACTUAL = SourceDef(
    ReportSource.PLAN_ACTUAL,
    "Plan/Ist",
    "Eine Zeile je Kostenstelle und Planmonat (Kostenstellen mit Plan)",
    (
        ColumnDef("cost_center", "Kostenstelle", _TEXT, groupable=True),
        ColumnDef("year", "Jahr", _INT, groupable=True),
        ColumnDef("month", "Monat", _INT, groupable=True),
        ColumnDef("status", "Status", _TEXT, groupable=True),
        ColumnDef("debit", "Soll", _MONEY, _ADD),
        ColumnDef("credit", "Haben", _MONEY, _ADD),
        ColumnDef("movement", "Ist-Bewegung", _MONEY, _ADD),
        ColumnDef("plan", "Monatsplan", _MONEY, _ADD),
        ColumnDef("deviation", "Abweichung", _MONEY, _ADD),
        ColumnDef("budget", "Ansatz", _MONEY),
        ColumnDef("remaining_budget", "Restansatz", _MONEY),
        ColumnDef("reserve_contribution", "Zuführung", _MONEY, _ADD),
        ColumnDef("reserve_release", "Entlastung", _MONEY, _ADD),
        ColumnDef("reserve_balance", "Rückstellungsbestand", _MONEY),
    ),
)

ACCOUNTS = SourceDef(
    ReportSource.ACCOUNTS,
    "Konten",
    "Eine Zeile je Konto",
    (
        ColumnDef("account", "Konto", _TEXT, groupable=True),
        ColumnDef("account_type", "Art", _TEXT, groupable=True),
        ColumnDef("status", "Status", _TEXT, groupable=True),
        ColumnDef("opening_balance", "Anfangssaldo", _MONEY),
        ColumnDef("debit", "Soll", _MONEY, _ADD),
        ColumnDef("credit", "Haben", _MONEY, _ADD),
        ColumnDef("balance", "Saldo", _MONEY),
    ),
)

SOURCES: dict[ReportSource, SourceDef] = {
    source.source: source for source in (BOOKINGS, PLAN_ACTUAL, ACCOUNTS)
}


def get_source(source: ReportSource) -> SourceDef:
    return SOURCES[source]
