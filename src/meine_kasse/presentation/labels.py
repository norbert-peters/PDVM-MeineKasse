"""Deutsche Beschriftungen für fachliche Werte."""

from datetime import date

from meine_kasse.domain.enums import AccountType, BookingType, CostCenterKind, IncomeMode

BOOKING_TYPE_LABELS = {
    BookingType.COST_CENTER_TO_ACCOUNT: "Kostenstelle → Konto",
    BookingType.ACCOUNT_TO_ACCOUNT: "Konto → Konto (Umbuchung)",
    BookingType.BUDGET_TRANSFER: "Ansatz Kostenstelle → Ansatz Kostenstelle",
}

# Beschriftung der führenden und der zweiten Stelle sowie Hinweis zur Wirkung von Soll/Haben
BOOKING_TYPE_FIELDS = {
    BookingType.COST_CENTER_TO_ACCOUNT: (
        "Kostenstelle:",
        "Konto:",
        "Soll: Kostenstelle und Konto werden belastet (Ausgabe). "
        "Haben: Zufluss auf beide Stellen (z. B. Einnahme, Erstattung).",
    ),
    BookingType.ACCOUNT_TO_ACCOUNT: (
        "Konto (führend):",
        "Gegenkonto:",
        "Soll: Das führende Konto wird belastet, das Gegenkonto erhält den Betrag. "
        "Haben: umgekehrt.",
    ),
    BookingType.BUDGET_TRANSFER: (
        "Kostenstelle (führend):",
        "Gegen-Kostenstelle:",
        "Soll: Die führende Kostenstelle gibt Ansatz ab, die Gegen-Kostenstelle erhält ihn. "
        "Haben: umgekehrt. Ist-Werte und Konten bleiben unberührt.",
    ),
}

MONTH_NAMES = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]

ACCOUNT_TYPE_LABELS = {
    AccountType.CHECKING: "Giro",
    AccountType.SAVINGS: "Spar",
    AccountType.INVESTMENT: "Anlage",
    AccountType.RESERVE: "Rückstellung",
}

COST_CENTER_KIND_LABELS = {
    CostCenterKind.STANDARD: "Standard (mit Plan)",
    CostCenterKind.WITHOUT_PLAN: "Ohne Plan",
    CostCenterKind.INCOME: "Einnahme",
}

INCOME_MODE_LABELS = {
    IncomeMode.PLAN: "Nach Plan verfügbar (z. B. Rente)",
    IncomeMode.ACTUAL: "Nur nach Ist verfügbar (z. B. Zinsen)",
}


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def format_iban(iban: str | None) -> str:
    """Gruppiert eine IBAN in Vierergruppen für die Anzeige."""
    if not iban:
        return ""
    return " ".join(iban[index : index + 4] for index in range(0, len(iban), 4))
