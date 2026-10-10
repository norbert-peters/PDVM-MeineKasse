"""Deutsche Beschriftungen für fachliche Werte."""

from datetime import date

from meine_kasse.domain.enums import AccountType, CostCenterKind

ACCOUNT_TYPE_LABELS = {
    AccountType.CHECKING: "Giro",
    AccountType.SAVINGS: "Spar",
    AccountType.INVESTMENT: "Anlage",
    AccountType.RESERVE: "Rückstellung",
}

COST_CENTER_KIND_LABELS = {
    CostCenterKind.STANDARD: "Standard (mit Plan)",
    CostCenterKind.WITHOUT_PLAN: "Ohne Plan",
}


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def format_iban(iban: str | None) -> str:
    """Gruppiert eine IBAN in Vierergruppen für die Anzeige."""
    if not iban:
        return ""
    return " ".join(iban[index : index + 4] for index in range(0, len(iban), 4))
