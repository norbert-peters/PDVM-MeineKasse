"""Sortierschlüssel für Tabellenzellen.

Tabellen zeigen formatierten Text („1.234,56 €“, „15.01.2026“). Sortiert wird nach dem Wert,
nie nach dem Anzeigetext. Wo die Rohwerte bekannt sind, werden sie explizit übergeben; sonst
leitet `sort_key_for_text` den Wert aus der deutschen Formatierung ab.
"""

import re
from datetime import date
from decimal import Decimal
from typing import Any

_EURO = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?\s*€$|^-?\d+(,\d+)?\s*€$")
_NUMBER = re.compile(r"^-?\d+(,\d+)?$")
_DATE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
_CHUNKS = re.compile(r"(\d+)")

_EMPTY = 0
_NUMERIC = 1
_DATE_RANK = 2
_TEXT = 3

SortKey = tuple[Any, ...]


def sort_key_for_text(text: str) -> SortKey:
    """Leere Zellen stehen vorn, dann Zahlen/Beträge, Datumswerte und Text (natürlich sortiert)."""
    value = text.strip()
    if not value:
        return (_EMPTY,)
    if _EURO.match(value):
        number = value.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
        return (_NUMERIC, Decimal(number))
    if _NUMBER.match(value):
        return (_NUMERIC, Decimal(value.replace(",", ".")))
    match = _DATE.match(value)
    if match:
        day, month, year = (int(part) for part in match.groups())
        try:
            return (_DATE_RANK, date(year, month, day).toordinal())
        except ValueError:
            pass
    return (_TEXT, natural_key(value))


def natural_key(text: str) -> tuple[tuple[int, int, str], ...]:
    """Zerlegt Text in Zahlen- und Textteile, sodass „Konto 2“ vor „Konto 10“ steht."""
    parts = []
    for chunk in _CHUNKS.split(text.casefold()):
        if not chunk:
            continue
        parts.append((0, int(chunk), "") if chunk.isdigit() else (1, 0, chunk))
    return tuple(parts)


def explicit_key(value: object | None) -> SortKey:
    """Schlüssel aus einem Rohwert (Cent, Datum, Text). `None` steht vorn."""
    if value is None:
        return (_EMPTY,)
    return (_NUMERIC, value)
