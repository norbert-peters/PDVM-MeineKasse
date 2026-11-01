"""Tabellenkomponente mit Spaltenfilter und einstufiger Sortierung (Architekturvorgabe 2.14).

- Unter jeder Spaltenüberschrift steht ein Suchfeld. Es blendet Zeilen aus, deren Text den
  Suchbegriff nicht enthält (ohne Beachtung der Groß-/Kleinschreibung, alle Felder müssen passen).
- Ein Klick auf die Überschrift sortiert auf- bzw. absteigend nach dieser einen Spalte.
  Sortiert wird nach Rohwerten (Cent, Datum), nicht nach dem Anzeigetext.
- Die Sortierung wird je Anwender und Tabelle gespeichert, sofern Einstellungen übergeben werden.

Verwendung: Zeilen in `table` füllen (Zellen als `SortItem`), danach `apply()` aufrufen.
"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.application.reporting.pdf_model import PdfColumn, PdfRow, PdfTable
from meine_kasse.application.services.user_settings_service import TableSort, UserSettingsService
from meine_kasse.domain.errors import DomainError
from meine_kasse.presentation.widgets.pdf_export import PdfExporter
from meine_kasse.presentation.widgets.sorting import SortKey, explicit_key, sort_key_for_text

AUTO = object()
_EDITOR_PADDING = 10


class SortItem(QTableWidgetItem):
    """Tabellenzelle mit Sortierschlüssel. Ohne `sort_value` wird er aus dem Text abgeleitet."""

    def __init__(self, text: str = "", *, sort_value: object = AUTO, row_id: str | None = None):
        super().__init__(text)
        self._key: SortKey = (
            sort_key_for_text(text) if sort_value is AUTO else explicit_key(sort_value)
        )
        if row_id is not None:
            self.setData(Qt.ItemDataRole.UserRole, row_id)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortItem):
            return self._key < other._key
        return self.text().casefold() < other.text().casefold()


class TablePreferences:
    """Verbindet Tabellen mit den Einstellungen und der PDF-Ausgabe des angemeldeten Anwenders."""

    def __init__(
        self,
        service: UserSettingsService,
        user_id: str,
        exporter: PdfExporter | None = None,
    ) -> None:
        self._service = service
        self._user_id = user_id
        self.exporter = exporter

    def load(self, table_key: str) -> TableSort | None:
        try:
            return self._service.get_table_sort(self._user_id, table_key)
        except DomainError:
            return None

    def save(self, table_key: str, sort: TableSort | None) -> None:
        try:
            self._service.save_table_sort(self._user_id, table_key, sort)
        except DomainError:
            return  # Die Sortierung bleibt für die Sitzung wirksam, nur das Merken entfällt.


class FilterHeader(QHeaderView):
    """Spaltenkopf mit einem Suchfeld je Spalte unterhalb der Überschrift."""

    filters_changed = Signal()

    def __init__(self, table: QTableWidget) -> None:
        super().__init__(Qt.Orientation.Horizontal, table)
        self._editors: list[QLineEdit] = []
        self.setSectionsClickable(True)
        self.setSortIndicatorShown(True)
        self.sectionResized.connect(lambda *_args: self._place_editors())
        self.sectionMoved.connect(lambda *_args: self._place_editors())
        self.geometriesChanged.connect(self._place_editors)
        table.horizontalScrollBar().valueChanged.connect(lambda _value: self._place_editors())

    def set_filter_count(self, count: int) -> None:
        for editor in self._editors:
            editor.deleteLater()
        self._editors = []
        for _ in range(count):
            editor = QLineEdit(self)
            editor.setPlaceholderText("Filter")
            editor.setClearButtonEnabled(True)
            editor.textChanged.connect(lambda _text: self.filters_changed.emit())
            editor.show()
            self._editors.append(editor)
        self.updateGeometries()

    def editor(self, column: int) -> QLineEdit:
        return self._editors[column]

    def texts(self) -> list[str]:
        return [editor.text().strip().casefold() for editor in self._editors]

    def raw_texts(self) -> list[str]:
        return [editor.text().strip() for editor in self._editors]

    def sizeHint(self) -> QSize:
        size = super().sizeHint()
        if self._editors:
            size.setHeight(size.height() + self._editor_height())
        return size

    def updateGeometries(self) -> None:
        self.setViewportMargins(0, 0, 0, self._editor_height() if self._editors else 0)
        super().updateGeometries()
        self._place_editors()

    def _editor_height(self) -> int:
        return self.fontMetrics().height() + _EDITOR_PADDING

    def _place_editors(self) -> None:
        height = self._editor_height()
        for column, editor in enumerate(self._editors):
            if self.isSectionHidden(column):
                editor.hide()
                continue
            editor.setGeometry(
                self.sectionViewportPosition(column),
                max(self.height() - height, 0),
                self.sectionSize(column),
                height,
            )
            editor.show()


class DataTable(QWidget):
    """Tabelle mit Spaltenfiltern und Sortierung. Die eigentliche Tabelle ist `table`."""

    def __init__(
        self,
        columns: Sequence[str],
        *,
        table_key: str,
        preferences: TablePreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._columns = list(columns)
        self._table_key = table_key
        self._preferences = preferences

        self.table = QTableWidget(0, len(self._columns), self)
        self._header = FilterHeader(self.table)
        self.table.setHorizontalHeader(self._header)
        self.table.setHorizontalHeaderLabels(self._columns)
        self._header.set_filter_count(len(self._columns))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        self._header.sectionClicked.connect(self._on_header_clicked)
        self._header.filters_changed.connect(self.apply_filters)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

        self._sort: TableSort | None = None
        saved = preferences.load(table_key) if preferences is not None else None
        if saved is not None and saved.column in self._columns:
            self._sort = saved
        self._show_sort_indicator()

    # Zustand

    @property
    def sort(self) -> TableSort | None:
        return self._sort

    def filter_edit(self, column: int) -> QLineEdit:
        return self._header.editor(column)

    def set_sort(self, column: str, *, ascending: bool = True, save: bool = True) -> None:
        if column not in self._columns:
            raise ValueError(f"Unbekannte Spalte: {column}")
        self._sort = TableSort(column, ascending)
        if save and self._preferences is not None:
            self._preferences.save(self._table_key, self._sort)
        self._show_sort_indicator()
        self.apply()

    # Anwenden

    def apply(self) -> None:
        """Sortiert und filtert die aktuellen Zeilen. Nach jedem Füllen der Tabelle aufrufen."""
        if self._sort is not None:
            order = (
                Qt.SortOrder.AscendingOrder
                if self._sort.ascending
                else Qt.SortOrder.DescendingOrder
            )
            self.table.sortItems(self._columns.index(self._sort.column), order)
        self.apply_filters()

    def apply_filters(self) -> None:
        needles = self._header.texts()
        for row in range(self.table.rowCount()):
            hidden = any(
                needle and needle not in self._cell_text(row, column)
                for column, needle in enumerate(needles)
            )
            self.table.setRowHidden(row, hidden)
        current = self.table.currentRow()
        if current >= 0 and self.table.isRowHidden(current):
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)

    # Auswahl

    def selected_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None
        item = self.table.item(row, 0)
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def select_id(self, row_id: str | None) -> None:
        if row_id is None:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if (
                item is not None
                and not self.table.isRowHidden(row)
                and item.data(Qt.ItemDataRole.UserRole) == row_id
            ):
                self.table.selectRow(row)
                return

    def visible_rows(self) -> list[list[str]]:
        """Angezeigte Zeilen in Anzeigereihenfolge (Grundlage der PDF-Ausgabe)."""
        return [
            [self._raw_text(row, column) for column in range(len(self._columns))]
            for row in self._visible_row_numbers()
        ]

    # PDF-Ausgabe

    def pdf_table(self, title: str, subtitle_lines: Sequence[str] = ()) -> PdfTable:
        """Die Tabelle „wie dargestellt“ (gefiltert, sortiert) für die PDF-Ausgabe."""
        visible = self._visible_row_numbers()
        columns = tuple(
            PdfColumn(name, align_right=self._is_right_aligned(visible, index))
            for index, name in enumerate(self._columns)
        )
        rows = tuple(PdfRow(tuple(cells)) for cells in self.visible_rows())
        lines = (*subtitle_lines, *self._view_description(), f"{len(rows)} Zeilen")
        return PdfTable(title=title, columns=columns, rows=rows, subtitle_lines=lines)

    def pdf_button(
        self,
        title: str | Callable[[], str],
        subtitle_lines: Callable[[], Sequence[str]] | None = None,
    ) -> QPushButton | None:
        """Schaltfläche „PDF“; `None`, wenn für den Anwender keine PDF-Ausgabe eingerichtet ist."""
        exporter = None if self._preferences is None else self._preferences.exporter
        if exporter is None:
            return None
        button = QPushButton("&PDF…")
        button.setToolTip("Die Tabelle wie dargestellt (gefiltert, sortiert) als PDF ausgeben")

        def export() -> None:
            name = title if isinstance(title, str) else title()
            lines = () if subtitle_lines is None else subtitle_lines()
            exporter.export(self, self.pdf_table(name, lines))

        button.clicked.connect(lambda _checked=False: export())
        return button

    # Intern

    def _visible_row_numbers(self) -> list[int]:
        return [row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)]

    def _is_right_aligned(self, rows: Sequence[int], column: int) -> bool:
        if not rows:
            return False
        item = self.table.item(rows[0], column)
        if item is None:
            return False
        alignment = item.textAlignment()
        flags = int(getattr(alignment, "value", alignment))
        return bool(flags & Qt.AlignmentFlag.AlignRight.value)

    def _view_description(self) -> list[str]:
        lines = []
        filters = [
            f"{name} enthält „{text}“"
            for name, text in zip(self._columns, self._header.raw_texts(), strict=True)
            if text
        ]
        if filters:
            lines.append("Filter: " + "; ".join(filters))
        if self._sort is not None:
            direction = "aufsteigend" if self._sort.ascending else "absteigend"
            lines.append(f"Sortierung: {self._sort.column} {direction}")
        return lines

    def _raw_text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return "" if item is None else item.text()

    def _cell_text(self, row: int, column: int) -> str:
        return self._raw_text(row, column).casefold()

    def _on_header_clicked(self, section: int) -> None:
        column = self._columns[section]
        ascending = not (
            self._sort is not None and self._sort.column == column and self._sort.ascending
        )
        self.set_sort(column, ascending=ascending)

    def _show_sort_indicator(self) -> None:
        if self._sort is None:
            self._header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
            return
        order = (
            Qt.SortOrder.AscendingOrder if self._sort.ascending else Qt.SortOrder.DescendingOrder
        )
        self._header.setSortIndicator(self._columns.index(self._sort.column), order)
