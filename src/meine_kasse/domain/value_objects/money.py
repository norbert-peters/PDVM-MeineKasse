"""Geldbeträge als ganzzahlige Cent (mit Vorzeichen) und Prozentwerte als Decimal.

`float` wird nirgends verwendet. Beträge werden ausschließlich in Euro geführt.
"""

import re
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from meine_kasse.domain.errors import ValidationError

_GERMAN_AMOUNT = re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")
_MIN_PERCENT_PLACES = 3


def to_cents(amount: Decimal | int | str) -> int:
    """Wandelt Euro exakt in Cent um. Mehr als zwei Nachkommastellen sind unzulässig."""
    try:
        value = Decimal(amount)
    except InvalidOperation as error:
        raise ValidationError("Der Betrag ist keine gültige Zahl.") from error
    if not value.is_finite():
        raise ValidationError("Der Betrag ist keine gültige Zahl.")
    cents = value * 100
    if cents != cents.to_integral_value():
        raise ValidationError("Beträge dürfen höchstens zwei Nachkommastellen haben.")
    return int(cents)


def from_cents(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)


def format_euro(cents: int) -> str:
    """Formatiert Cent als deutschen Euro-Betrag, z. B. `-1.234,56 €`."""
    sign = "-" if cents < 0 else ""
    euros, rest = divmod(abs(cents), 100)
    return f"{sign}{euros:,}".replace(",", ".") + f",{rest:02d} €"


def parse_euro(text: str) -> int:
    """Liest einen deutschen Betrag wie `1.234,56`, `-5,5` oder `12 €` als Cent."""
    cleaned = text.replace("€", "").replace(" ", "").replace("\u00a0", "")
    if not _GERMAN_AMOUNT.match(cleaned):
        raise ValidationError("Der Betrag ist ungültig. Bitte im Format 1.234,56 eingeben.")
    return to_cents(cleaned.replace(".", "").replace(",", "."))


def format_percent(value: Decimal) -> str:
    """Formatiert einen Prozentwert mit mindestens drei Nachkommastellen."""
    exponent = value.as_tuple().exponent
    places = max(_MIN_PERCENT_PLACES, -exponent if isinstance(exponent, int) else 0)
    return f"{value:.{places}f}".replace(".", ",") + " %"


def allocate_by_percent(total_cents: int, percentages: Sequence[Decimal]) -> list[int]:
    """Teilt einen Betrag prozentual auf.

    Teilbeträge behalten das Vorzeichen des Gesamtbetrags. Eine Rundungsdifferenz wird dem
    größten Anteil (bei Gleichstand dem ersten) zugeschlagen, damit die Summe stimmt.
    """
    if not percentages:
        raise ValidationError("Für die Aufteilung ist mindestens ein Anteil nötig.")
    if any(share < 0 for share in percentages):
        raise ValidationError("Prozentanteile dürfen nicht negativ sein.")
    if sum(percentages, Decimal(0)) != Decimal(100):
        raise ValidationError("Die Prozentanteile müssen zusammen genau 100 % ergeben.")

    sign = -1 if total_cents < 0 else 1
    magnitude = abs(total_cents)
    parts = [
        int((Decimal(magnitude) * share / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        for share in percentages
    ]
    largest = max(range(len(percentages)), key=lambda index: (percentages[index], -index))
    parts[largest] += magnitude - sum(parts)
    return [sign * part for part in parts]
