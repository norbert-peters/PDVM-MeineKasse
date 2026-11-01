"""Modell einer PDF-Tabelle. Es ist unabhängig von der Erzeugung (Port `PdfRenderer`)."""

from dataclasses import dataclass
from enum import StrEnum


class RowStyle(StrEnum):
    NORMAL = "NORMAL"
    GROUP = "GROUP"
    SUBTOTAL = "SUBTOTAL"
    TOTAL = "TOTAL"


@dataclass(frozen=True, slots=True)
class PdfColumn:
    header: str
    align_right: bool = False


@dataclass(frozen=True, slots=True)
class PdfRow:
    cells: tuple[str, ...]
    style: RowStyle = RowStyle.NORMAL


@dataclass(frozen=True, slots=True)
class PdfTable:
    """Tabelle für die PDF-Ausgabe. Die Gesamtzeile steht unmittelbar unter der Kopfzeile."""

    title: str
    columns: tuple[PdfColumn, ...]
    rows: tuple[PdfRow, ...]
    subtitle_lines: tuple[str, ...] = ()
    total_row: PdfRow | None = None
