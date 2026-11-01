"""Dateinamen im Dokumentenarchiv (Architekturvorgabe 2.14).

Der Name besteht aus einem maschinellen Teil (Zeitstempel, Tabellenname) und einem manuellen
Zusatz von höchstens 40 Zeichen. Unzulässige Dateizeichen werden entfernt.
"""

import re
from datetime import datetime

from meine_kasse.domain.errors import ValidationError

MAX_SUFFIX_LENGTH = 40
MAX_TABLE_NAME_LENGTH = 60
PDF_EXTENSION = ".pdf"

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_FALLBACK_TABLE_NAME = "Tabelle"


def sanitize_name_part(text: str) -> str:
    """Entfernt unzulässige Dateizeichen, ersetzt Leerraum durch `_` und kürzt Randzeichen."""
    cleaned = _FORBIDDEN.sub("", text)
    cleaned = _WHITESPACE.sub("_", cleaned.strip())
    return cleaned.strip("._")


def clean_suffix(suffix: str) -> str:
    """Bereinigter manueller Zusatz. Mehr als 40 eingegebene Zeichen werden abgelehnt."""
    if len(suffix.strip()) > MAX_SUFFIX_LENGTH:
        raise ValidationError(
            f"Der Zusatz für den Dateinamen darf höchstens {MAX_SUFFIX_LENGTH} Zeichen lang sein."
        )
    return sanitize_name_part(suffix)[:MAX_SUFFIX_LENGTH]


def build_file_name(moment: datetime, table_name: str, suffix: str = "") -> str:
    """Dateiname nach dem Muster `2026-05-15_143000_Buchungen[_Zusatz].pdf`."""
    table_part = sanitize_name_part(table_name)[:MAX_TABLE_NAME_LENGTH] or _FALLBACK_TABLE_NAME
    parts = [f"{moment:%Y-%m-%d_%H%M%S}", table_part]
    cleaned = clean_suffix(suffix)
    if cleaned:
        parts.append(cleaned)
    return "_".join(parts) + PDF_EXTENSION
