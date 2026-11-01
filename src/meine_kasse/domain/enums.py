"""Zentrale Aufzählungen. Die Werte werden unverändert in der Datenbank gespeichert."""

from enum import StrEnum


class Side(StrEnum):
    """Buchungsseite. Soll = Abfluss/Verbrauch, Haben = Zufluss/Verfügbares."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class BookingType(StrEnum):
    COST_CENTER_TO_ACCOUNT = "COST_CENTER_TO_ACCOUNT"
    ACCOUNT_TO_ACCOUNT = "ACCOUNT_TO_ACCOUNT"
    BUDGET_TRANSFER = "BUDGET_TRANSFER"


class ObjectKind(StrEnum):
    COST_CENTER = "COST_CENTER"
    ACCOUNT = "ACCOUNT"


class AccountType(StrEnum):
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    INVESTMENT = "INVESTMENT"
    RESERVE = "RESERVE"


class CostCenterKind(StrEnum):
    STANDARD = "STANDARD"
    WITHOUT_PLAN = "WITHOUT_PLAN"
    INCOME = "INCOME"


class IncomeMode(StrEnum):
    """Wann eine Einnahme per Ansatzumbuchung weitergegeben werden darf (Vorgabe 2.15)."""

    PLAN = "PLAN"
    ACTUAL = "ACTUAL"


class PlanMode(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    IRREGULAR = "IRREGULAR"
    RESERVE = "RESERVE"


class ClosureKind(StrEnum):
    MONTH = "MONTH"
    YEAR = "YEAR"


class DocumentType(StrEnum):
    """Herkunft einer PDF-Datei im Dokumentenarchiv (Vorgabe 2.14)."""

    TABLE = "TABLE"
    REPORT = "REPORT"


class ReportSource(StrEnum):
    """Datenquelle einer Auswertung mit fester Zeilenbedeutung (Vorgabe 2.14)."""

    BOOKINGS = "BOOKINGS"
    PLAN_ACTUAL = "PLAN_ACTUAL"
    ACCOUNTS = "ACCOUNTS"


class FilterOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    CONTAINS = "CONTAINS"
    GREATER = "GREATER"
    GREATER_OR_EQUAL = "GREATER_OR_EQUAL"
    LESS = "LESS"
    LESS_OR_EQUAL = "LESS_OR_EQUAL"
