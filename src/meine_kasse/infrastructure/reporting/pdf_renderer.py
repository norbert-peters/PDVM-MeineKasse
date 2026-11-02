"""PDF-Erzeugung mit reportlab (Umsetzung des Ports `PdfRenderer`, Architekturvorgabe 3.1)."""

from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from meine_kasse.application.reporting.pdf_model import PdfRow, PdfTable, RowStyle

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONT_SIZE = 8
_LANDSCAPE_FROM_COLUMNS = 6
_MARGIN = 15 * mm
_MIN_COLUMN_WIDTH = 18 * mm
_MAX_TEXT_WIDTH = 90 * mm
_PADDING = 4
# Die Standardschrift (WinAnsi) kennt diese Zeichen nicht; sie werden ersetzt.
_SUBSTITUTIONS = {"→": "->", "−": "-", "–": "-", "…": "...", "\u00a0": " "}

_ROW_BACKGROUND = {
    RowStyle.GROUP: colors.Color(0.88, 0.91, 0.96),
    RowStyle.SUBTOTAL: colors.Color(0.94, 0.94, 0.94),
    RowStyle.TOTAL: colors.Color(0.82, 0.88, 0.82),
}


def _printable(text: str) -> str:
    for source, replacement in _SUBSTITUTIONS.items():
        text = text.replace(source, replacement)
    return text.encode("cp1252", errors="replace").decode("cp1252")


class ReportlabPdfRenderer:
    def render(self, table: PdfTable, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        page = landscape(A4) if len(table.columns) >= _LANDSCAPE_FROM_COLUMNS else A4
        document = SimpleDocTemplate(
            str(target),
            pagesize=page,
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=_MARGIN,
            bottomMargin=_MARGIN,
            title=_printable(table.title),
            author="Meine Kasse",
        )
        created = f"Erstellt am {datetime.now():%d.%m.%Y %H:%M}"

        def footer(canvas: Any, doc: Any) -> None:
            canvas.saveState()
            canvas.setFont(_FONT, _FONT_SIZE)
            canvas.drawString(_MARGIN, 8 * mm, created)
            canvas.drawRightString(page[0] - _MARGIN, 8 * mm, f"Seite {doc.page}")
            canvas.restoreState()

        styles = getSampleStyleSheet()
        story: list[Any] = [Paragraph(escape(_printable(table.title)), styles["Title"])]
        for line in table.subtitle_lines:
            story.append(Paragraph(escape(_printable(line)), styles["Normal"]))
        story.append(Spacer(1, 4 * mm))
        story.append(self._build_table(table, page[0] - 2 * _MARGIN))
        document.build(story, onFirstPage=footer, onLaterPages=footer)

    def _build_table(self, table: PdfTable, available: float) -> Table:
        body = ([table.total_row] if table.total_row else []) + list(table.rows)
        widths = _column_widths(table, body, available)
        header = [
            self._cell(column.header, True, column.align_right, colors.white)
            for column in table.columns
        ]
        data = [header]
        commands: list[tuple[Any, ...]] = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.2, 0.3, 0.45)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.Color(0.7, 0.7, 0.7)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for index, row in enumerate(body, start=1):
            bold = row.style is not RowStyle.NORMAL
            data.append(
                [
                    self._cell(text, bold, table.columns[column].align_right)
                    for column, text in enumerate(row.cells)
                ]
            )
            if row.style in _ROW_BACKGROUND:
                commands.append(("BACKGROUND", (0, index), (-1, index), _ROW_BACKGROUND[row.style]))
        result = Table(data, colWidths=widths, repeatRows=1)
        result.setStyle(TableStyle(commands))
        return result

    @staticmethod
    def _cell(
        text: str, bold: bool, align_right: bool, text_color: Any = colors.black
    ) -> Paragraph:
        # TEXTCOLOR des TableStyle wirkt nicht auf Paragraphs, daher hier setzen.
        style = ParagraphStyle(
            "cell",
            fontName=_FONT_BOLD if bold else _FONT,
            fontSize=_FONT_SIZE,
            leading=_FONT_SIZE + 2,
            alignment=2 if align_right else 0,
            textColor=text_color,
        )
        return Paragraph(escape(_printable(text)), style)


def _column_widths(table: PdfTable, rows: list[PdfRow], available: float) -> list[float]:
    wanted: list[float] = []
    for index, column in enumerate(table.columns):
        widest = stringWidth(_printable(column.header), _FONT_BOLD, _FONT_SIZE)
        for row in rows:
            widest = max(widest, stringWidth(_printable(row.cells[index]), _FONT_BOLD, _FONT_SIZE))
        wanted.append(min(max(widest + 2 * _PADDING, _MIN_COLUMN_WIDTH), _MAX_TEXT_WIDTH))
    total = sum(wanted)
    scale = available / total if total else 1.0
    return [width * scale for width in wanted]
