"""Auswertungsmaschine: Filter, Sortierung, Gruppierung und Summen (Architekturvorgabe 2.14).

Die Maschine arbeitet auf Quellzeilen (Spaltenschlüssel → Rohwert) und kennt keine Datenbank. Filter
sind strukturierte Bedingungen aus dem Katalog, freies SQL gibt es nicht. Summen bilden nur
`ADDITIVE`-Spalten; in Gruppensummen zeigen `NON_ADDITIVE`-Beträge den Wert der letzten Zeile
der Gruppe, in der Gesamtzeile erscheint dafür nichts.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import groupby
from typing import Any

from meine_kasse.application.reporting.catalog import (
    MAX_GROUP_LEVELS,
    OPERATOR_LABELS,
    ColumnDef,
    ColumnKind,
    SourceDef,
    get_source,
)
from meine_kasse.application.reporting.pdf_model import PdfColumn, PdfRow, PdfTable, RowStyle
from meine_kasse.domain.entities import ReportDefinition, ReportFilter
from meine_kasse.domain.enums import FilterOperator
from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.value_objects.money import format_euro, parse_euro

SourceRow = Mapping[str, Any]
_TOTAL_LABEL = "Gesamt"
_EMPTY_GROUP = "(leer)"


@dataclass(frozen=True, slots=True)
class ReportResult:
    """Ergebnis einer Auswertung. Die Gesamtzeile gehört in den Kopf der Ausgabe."""

    title: str
    columns: tuple[ColumnDef, ...]
    total_row: PdfRow
    rows: tuple[PdfRow, ...]
    row_count: int
    filter_lines: tuple[str, ...] = ()

    def to_pdf_table(self) -> PdfTable:
        return PdfTable(
            title=self.title,
            columns=tuple(
                PdfColumn(column.label, align_right=_is_numeric(column)) for column in self.columns
            ),
            rows=self.rows,
            subtitle_lines=(*self.filter_lines, f"{self.row_count} Zeilen"),
            total_row=self.total_row,
        )


def validate_definition(definition: ReportDefinition) -> SourceDef:
    """Prüft die Definition gegen den Katalog und liefert die Datenquelle."""
    source = get_source(definition.data_source)
    if not definition.columns:
        raise ValidationError("Bitte mindestens eine Spalte auswählen.")
    if len(set(definition.columns)) != len(definition.columns):
        raise ValidationError("Eine Spalte darf nur einmal ausgewählt werden.")
    for key in definition.columns:
        _column(source, key)
    for condition in definition.filters:
        column = _column(source, condition.column)
        if condition.operator not in column.operators:
            raise ValidationError(f"Der Operator passt nicht zur Spalte '{column.label}'.")
        parse_filter_value(column, condition.value)
    if definition.sort is not None:
        _selected(definition, definition.sort.column, "Sortierung")
    if len(definition.groups) > MAX_GROUP_LEVELS:
        raise ValidationError(f"Es sind höchstens {MAX_GROUP_LEVELS} Gruppenebenen möglich.")
    if len({group.column for group in definition.groups}) != len(definition.groups):
        raise ValidationError("Eine Spalte kann nur eine Gruppenebene bilden.")
    for group in definition.groups:
        column = _selected(definition, group.column, "Gruppierung")
        if not column.groupable:
            raise ValidationError(f"Nach der Spalte '{column.label}' kann nicht gruppiert werden.")
    return source


def parse_filter_value(column: ColumnDef, text: str) -> Any:
    """Wandelt den eingegebenen Filterwert in den Vergleichswert der Spalte um."""
    value = text.strip()
    if column.kind is ColumnKind.TEXT:
        return value.casefold()
    if not value:
        raise ValidationError(f"Für die Spalte '{column.label}' fehlt der Vergleichswert.")
    if column.kind is ColumnKind.MONEY:
        return parse_euro(value)
    if column.kind is ColumnKind.INT:
        try:
            return int(value)
        except ValueError as error:
            raise ValidationError(
                f"Der Wert für '{column.label}' muss eine ganze Zahl sein."
            ) from error
    return _parse_date(value, column)


def run_report(definition: ReportDefinition, source_rows: Sequence[SourceRow]) -> ReportResult:
    source = validate_definition(definition)
    columns = tuple(_column(source, key) for key in definition.columns)
    rows = [row for row in source_rows if _matches_all(source, definition.filters, row)]

    if definition.sort is not None:
        sort_column = _column(source, definition.sort.column)
        rows.sort(key=_key_function(sort_column), reverse=not definition.sort.ascending)
    group_columns = [_column(source, group.column) for group in definition.groups]
    for column in reversed(group_columns):
        rows.sort(key=_key_function(column))

    output: list[PdfRow] = []
    _emit(rows, 0, definition, group_columns, columns, output)
    return ReportResult(
        title=definition.name or source.label,
        columns=columns,
        total_row=_total_row(columns, rows),
        rows=tuple(output),
        row_count=len(rows),
        filter_lines=_filter_lines(source, definition),
    )


def display_value(column: ColumnDef, value: Any) -> str:
    if value is None:
        return ""
    if column.kind is ColumnKind.MONEY:
        return format_euro(int(value))
    if column.kind is ColumnKind.DATE:
        return str(value.strftime("%d.%m.%Y"))
    return str(value)


# Intern


def _column(source: SourceDef, key: str) -> ColumnDef:
    column = source.column(key)
    if column is None:
        raise ValidationError(f"Die Spalte '{key}' gehört nicht zur Datenquelle {source.label}.")
    return column


def _selected(definition: ReportDefinition, key: str, purpose: str) -> ColumnDef:
    source = get_source(definition.data_source)
    column = _column(source, key)
    if key not in definition.columns:
        raise ValidationError(
            f"Die Spalte '{column.label}' der {purpose} muss in der Spaltenauswahl enthalten sein."
        )
    return column


def _is_numeric(column: ColumnDef) -> bool:
    return column.kind in (ColumnKind.MONEY, ColumnKind.INT)


def _parse_date(text: str, column: ColumnDef) -> date:
    try:
        if "." in text:
            day, month, year = (int(part) for part in text.split("."))
            return date(year, month, day)
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValidationError(
            f"Der Wert für '{column.label}' muss ein Datum sein (TT.MM.JJJJ)."
        ) from error


def _matches_all(source: SourceDef, filters: Sequence[ReportFilter], row: SourceRow) -> bool:
    for condition in filters:
        column = _column(source, condition.column)
        expected = parse_filter_value(column, condition.value)
        if not _matches(column, condition.operator, row.get(column.key), expected):
            return False
    return True


def _matches(column: ColumnDef, operator: FilterOperator, actual: Any, expected: Any) -> bool:
    if column.kind is ColumnKind.TEXT:
        text = ("" if actual is None else str(actual)).casefold()
        if operator is FilterOperator.CONTAINS:
            return bool(expected in text)
        if operator is FilterOperator.EQUALS:
            return bool(text == expected)
        return bool(text != expected)
    if actual is None:
        if column.kind is ColumnKind.DATE:
            return operator is FilterOperator.NOT_EQUALS
        actual = 0
    comparisons = {
        FilterOperator.EQUALS: actual == expected,
        FilterOperator.NOT_EQUALS: actual != expected,
        FilterOperator.GREATER: actual > expected,
        FilterOperator.GREATER_OR_EQUAL: actual >= expected,
        FilterOperator.LESS: actual < expected,
        FilterOperator.LESS_OR_EQUAL: actual <= expected,
    }
    return bool(comparisons[operator])


def _key_function(column: ColumnDef) -> Callable[[SourceRow], tuple[int, Any]]:
    return lambda row: _sort_key(column, row)


def _sort_key(column: ColumnDef, row: SourceRow) -> tuple[int, Any]:
    value = row.get(column.key)
    if value is None:
        return (0, 0)
    if column.kind is ColumnKind.TEXT:
        return (1, str(value).casefold())
    return (1, value)


def _emit(
    rows: Sequence[SourceRow],
    level: int,
    definition: ReportDefinition,
    group_columns: Sequence[ColumnDef],
    columns: Sequence[ColumnDef],
    output: list[PdfRow],
) -> None:
    if level == len(definition.groups):
        output.extend(
            PdfRow(tuple(display_value(column, row.get(column.key)) for column in columns))
            for row in rows
        )
        return
    group_column = group_columns[level]
    group = definition.groups[level]
    for value, members_iter in groupby(rows, key=lambda row: row.get(group_column.key)):
        members = list(members_iter)
        text = display_value(group_column, value) or _EMPTY_GROUP
        if not group.summary_only:
            output.append(
                _marker_row(columns, group_column, f"{group_column.label}: {text}", RowStyle.GROUP)
            )
            _emit(members, level + 1, definition, group_columns, columns, output)
        output.append(_subtotal_row(columns, group_column, f"Summe {text}", members))


def _marker_row(
    columns: Sequence[ColumnDef], marker_column: ColumnDef, text: str, style: RowStyle
) -> PdfRow:
    return PdfRow(tuple(text if column is marker_column else "" for column in columns), style)


def _subtotal_row(
    columns: Sequence[ColumnDef],
    group_column: ColumnDef,
    label: str,
    members: Sequence[SourceRow],
) -> PdfRow:
    cells = []
    for column in columns:
        if column is group_column:
            cells.append(label)
        elif column.is_additive and _is_numeric(column):
            cells.append(display_value(column, _sum(column, members)))
        elif column.kind is ColumnKind.MONEY:
            cells.append(display_value(column, members[-1].get(column.key)))
        else:
            cells.append("")
    return PdfRow(tuple(cells), RowStyle.SUBTOTAL)


def _total_row(columns: Sequence[ColumnDef], rows: Sequence[SourceRow]) -> PdfRow:
    cells = []
    labelled = False
    for column in columns:
        if column.is_additive and _is_numeric(column):
            cells.append(display_value(column, _sum(column, rows)))
        elif not labelled:
            cells.append(_TOTAL_LABEL)
            labelled = True
        else:
            cells.append("")
    return PdfRow(tuple(cells), RowStyle.TOTAL)


def _sum(column: ColumnDef, rows: Sequence[SourceRow]) -> int:
    return sum(int(row.get(column.key) or 0) for row in rows)


def _filter_lines(source: SourceDef, definition: ReportDefinition) -> tuple[str, ...]:
    lines = [f"Datenquelle: {source.label}"]
    if definition.filters:
        conditions = [
            f"{_column(source, item.column).label} {OPERATOR_LABELS[item.operator]} {item.value}"
            for item in definition.filters
        ]
        lines.append("Filter: " + "; ".join(conditions))
    return tuple(lines)
