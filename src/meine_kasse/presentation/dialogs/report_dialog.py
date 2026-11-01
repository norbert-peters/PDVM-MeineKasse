from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.application.reporting.catalog import (
    MAX_GROUP_LEVELS,
    OPERATOR_LABELS,
    ColumnDef,
    ColumnKind,
    SourceDef,
)
from meine_kasse.application.reporting.engine import ReportResult
from meine_kasse.application.reporting.pdf_model import RowStyle
from meine_kasse.application.services.report_service import ReportService
from meine_kasse.domain.entities import ReportDefinition, ReportFilter, ReportGroup, ReportSort
from meine_kasse.domain.enums import FilterOperator
from meine_kasse.domain.errors import DomainError
from meine_kasse.presentation.widgets.pdf_export import PdfExporter

_NEW_REPORT = "(neue Auswertung)"
_NO_SELECTION = "(keine)"
_BAD = "color: #b00020;"
_GROUP_BACKGROUND = QBrush(QColor("#e1e8f5"))
_SUBTOTAL_BACKGROUND = QBrush(QColor("#efefef"))
_TOTAL_BACKGROUND = QBrush(QColor("#d2e2d2"))
_ROW_BACKGROUND = {
    RowStyle.GROUP: _GROUP_BACKGROUND,
    RowStyle.SUBTOTAL: _SUBTOTAL_BACKGROUND,
    RowStyle.TOTAL: _TOTAL_BACKGROUND,
}


class FilterRow(QWidget):
    """Eine Bedingung: Spalte, Operator, Wert. Die Operatoren folgen der Art der Spalte."""

    def __init__(self, source: SourceDef, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source = source
        self.column_combo = QComboBox()
        for column in source.columns:
            self.column_combo.addItem(column.label, column.key)
        self.operator_combo = QComboBox()
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("Wert, z. B. 12,50 oder 01.05.2026")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.column_combo, 2)
        layout.addWidget(self.operator_combo, 2)
        layout.addWidget(self.value_edit, 3)
        self.column_combo.currentIndexChanged.connect(lambda _index: self._load_operators())
        self._load_operators()

    def _column(self) -> ColumnDef:
        column = self._source.column(self.column_combo.currentData())
        if column is None:
            raise LookupError("Unbekannte Spalte")
        return column

    def _load_operators(self) -> None:
        keep = self.operator_combo.currentData()
        self.operator_combo.clear()
        for operator in self._column().operators:
            self.operator_combo.addItem(OPERATOR_LABELS[operator], operator.value)
        index = self.operator_combo.findData(keep)
        self.operator_combo.setCurrentIndex(max(index, 0))

    def set_filter(self, condition: ReportFilter) -> None:
        self.column_combo.setCurrentIndex(max(self.column_combo.findData(condition.column), 0))
        self.operator_combo.setCurrentIndex(
            max(self.operator_combo.findData(condition.operator.value), 0)
        )
        self.value_edit.setText(condition.value)

    def condition(self) -> ReportFilter:
        operator = FilterOperator(self.operator_combo.currentData())
        return ReportFilter(self.column_combo.currentData(), operator, self.value_edit.text())


class ReportDialog(QDialog):
    """Allgemeine Auswertung: Datenquelle, Spalten, Filter, Sortierung, Gruppierung, PDF.

    Auswertungen können je Anwender gespeichert werden. Es gibt kein freies SQL, Filter sind
    strukturierte Bedingungen aus dem Spaltenkatalog der Datenquelle.
    """

    def __init__(
        self,
        reports: ReportService,
        exporter: PdfExporter,
        user_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Auswertung")
        self.resize(1200, 780)
        self._reports = reports
        self._exporter = exporter
        self._user_id = user_id
        self._sources = list(reports.sources())
        self._saved: dict[str, ReportDefinition] = {}
        self._filter_rows: list[FilterRow] = []
        self._last_result: ReportResult | None = None

        self.source_combo = QComboBox()
        for source in self._sources:
            self.source_combo.addItem(f"{source.label} – {source.row_meaning}", source.source.value)
        self.saved_combo = QComboBox()
        self.save_button = self._button("&Speichern…", self._save)
        self.delete_button = self._button("Lös&chen", self._delete)

        top = QHBoxLayout()
        top.addWidget(QLabel("Datenquelle:"))
        top.addWidget(self.source_combo, 1)
        top.addWidget(QLabel("Gespeichert:"))
        top.addWidget(self.saved_combo, 1)
        top.addWidget(self.save_button)
        top.addWidget(self.delete_button)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_columns_tab(), "Spalten")
        self.tabs.addTab(self._build_filter_tab(), "Filter")
        self.tabs.addTab(self._build_sort_group_tab(), "Sortierung und Gruppierung")
        self.tabs.setMaximumHeight(230)

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.summary_label = QLabel()
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        self.run_button = self._button("&Auswerten", self.run)
        self.pdf_button = self._button("&PDF…", self._export_pdf)
        self.pdf_button.setEnabled(False)
        close_button = self._button("S&chließen", self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.pdf_button)
        buttons.addStretch()
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.tabs)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.message_label)
        layout.addLayout(buttons)

        self.source_combo.currentIndexChanged.connect(lambda _index: self._load_source())
        self.saved_combo.activated.connect(lambda _index: self._load_saved())
        self._reload_saved()
        self._load_source()

    # Aufbau

    def _button(self, text: str, handler: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False: handler())
        return button

    def _build_columns_tab(self) -> QWidget:
        self.column_list = QListWidget()
        self.up_button = self._button("Nach &oben", lambda: self._move_column(-1))
        self.down_button = self._button("Nach &unten", lambda: self._move_column(1))
        side = QVBoxLayout()
        side.addWidget(QLabel("Haken = Spalte erscheint, Reihenfolge wie in der Liste."))
        side.addWidget(self.up_button)
        side.addWidget(self.down_button)
        side.addStretch()
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.addWidget(self.column_list, 1)
        layout.addLayout(side)
        return tab

    def _build_filter_tab(self) -> QWidget:
        self.filter_layout = QVBoxLayout()
        self.filter_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        add_button = self._button("&Bedingung hinzufügen", self._add_filter)
        remove_button = self._button("Letzte Bedingung &entfernen", self._remove_filter)
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Alle Bedingungen müssen zutreffen (UND)."))
        layout.addLayout(self.filter_layout)
        row = QHBoxLayout()
        row.addWidget(add_button)
        row.addWidget(remove_button)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        return tab

    def _build_sort_group_tab(self) -> QWidget:
        self.sort_combo = QComboBox()
        self.sort_descending = QCheckBox("absteigend")
        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Sortieren nach:"))
        sort_row.addWidget(self.sort_combo, 1)
        sort_row.addWidget(self.sort_descending)

        self.group_combos: list[QComboBox] = []
        self.group_summary_only: list[QCheckBox] = []
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addLayout(sort_row)
        for level in range(MAX_GROUP_LEVELS):
            combo = QComboBox()
            only_sums = QCheckBox("nur Summen")
            row = QHBoxLayout()
            row.addWidget(QLabel(f"Gruppenebene {level + 1}:"))
            row.addWidget(combo, 1)
            row.addWidget(only_sums)
            layout.addLayout(row)
            self.group_combos.append(combo)
            self.group_summary_only.append(only_sums)
        layout.addStretch()
        return tab

    # Datenquelle und Spalten

    def _current_source(self) -> SourceDef:
        return self._sources[self.source_combo.currentIndex()]

    def _load_source(self, definition: ReportDefinition | None = None) -> None:
        source = self._current_source()
        self.column_list.clear()
        keys = list(definition.columns) if definition else [item.key for item in source.columns]
        ordered = [source.column(key) for key in keys if source.column(key) is not None]
        rest = [item for item in source.columns if item.key not in keys]
        for column in [*ordered, *rest]:
            if column is None:
                continue
            entry = QListWidgetItem(column.label)
            entry.setData(Qt.ItemDataRole.UserRole, column.key)
            entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = column.key in keys
            entry.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.column_list.addItem(entry)

        for row in self._filter_rows:
            row.setParent(None)
            row.deleteLater()
        self._filter_rows = []
        for condition in definition.filters if definition else ():
            self._add_filter(condition)

        self._load_choices(definition)
        self._clear_result()

    def _load_choices(self, definition: ReportDefinition | None) -> None:
        source = self._current_source()
        self.sort_combo.clear()
        self.sort_combo.addItem(_NO_SELECTION, None)
        for column in source.columns:
            self.sort_combo.addItem(column.label, column.key)
        sort = definition.sort if definition else None
        self.sort_combo.setCurrentIndex(
            max(self.sort_combo.findData(sort.column), 0) if sort else 0
        )
        self.sort_descending.setChecked(bool(sort and not sort.ascending))
        for level, (combo, only_sums) in enumerate(
            zip(self.group_combos, self.group_summary_only, strict=True)
        ):
            combo.clear()
            combo.addItem(_NO_SELECTION, None)
            for column in source.columns:
                if column.groupable:
                    combo.addItem(column.label, column.key)
            group = (
                definition.groups[level] if definition and level < len(definition.groups) else None
            )
            combo.setCurrentIndex(max(combo.findData(group.column), 0) if group else 0)
            only_sums.setChecked(bool(group and group.summary_only))

    def _move_column(self, step: int) -> None:
        row = self.column_list.currentRow()
        target = row + step
        if row < 0 or not 0 <= target < self.column_list.count():
            return
        entry = self.column_list.takeItem(row)
        self.column_list.insertItem(target, entry)
        self.column_list.setCurrentRow(target)

    # Filter

    def _add_filter(self, condition: ReportFilter | None = None) -> None:
        row = FilterRow(self._current_source())
        if isinstance(condition, ReportFilter):
            row.set_filter(condition)
        self.filter_layout.addWidget(row)
        self._filter_rows.append(row)

    def _remove_filter(self) -> None:
        if self._filter_rows:
            row = self._filter_rows.pop()
            row.setParent(None)
            row.deleteLater()

    # Definition

    def definition(self, name: str = "") -> ReportDefinition:
        columns = tuple(
            str(self.column_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.column_list.count())
            if self.column_list.item(index).checkState() == Qt.CheckState.Checked
        )
        sort_key = self.sort_combo.currentData()
        groups = tuple(
            ReportGroup(combo.currentData(), only_sums.isChecked())
            for combo, only_sums in zip(self.group_combos, self.group_summary_only, strict=True)
            if combo.currentData() is not None
        )
        return ReportDefinition(
            name=name,
            data_source=self._current_source().source,
            columns=columns,
            filters=tuple(row.condition() for row in self._filter_rows),
            sort=None
            if sort_key is None
            else ReportSort(sort_key, not self.sort_descending.isChecked()),
            groups=groups,
        )

    def apply_definition(self, definition: ReportDefinition) -> None:
        index = next(
            (i for i, item in enumerate(self._sources) if item.source is definition.data_source), 0
        )
        self.source_combo.blockSignals(True)
        self.source_combo.setCurrentIndex(index)
        self.source_combo.blockSignals(False)
        self._load_source(definition)

    # Gespeicherte Auswertungen

    def _reload_saved(self, select: str | None = None) -> None:
        try:
            saved = self._reports.list_definitions(self._user_id)
        except DomainError as error:
            self._show_message(str(error), error=True)
            return
        self._saved = {item.name: item for item in saved}
        self.saved_combo.clear()
        self.saved_combo.addItem(_NEW_REPORT, None)
        for name in self._saved:
            self.saved_combo.addItem(name, name)
        self.saved_combo.setCurrentIndex(max(self.saved_combo.findData(select), 0))
        self.delete_button.setEnabled(select in self._saved)

    def _load_saved(self) -> None:
        name = self.saved_combo.currentData()
        self.delete_button.setEnabled(name is not None)
        if name is not None and name in self._saved:
            self.apply_definition(self._saved[name])

    def _save(self) -> None:
        default = self.saved_combo.currentData() or ""
        name, accepted = QInputDialog.getText(
            self, "Auswertung speichern", "Name der Auswertung:", text=default
        )
        if not accepted:
            return
        name = name.strip()
        if name in self._saved and name != default:
            answer = QMessageBox.question(
                self, "Auswertung speichern", f"Die Auswertung '{name}' ersetzen?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self._reports.save_definition(self._user_id, self.definition(name))
        except DomainError as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))
            return
        self._reload_saved(select=name)
        self._show_message(f"Die Auswertung '{name}' wurde gespeichert.")

    def _delete(self) -> None:
        name = self.saved_combo.currentData()
        if name is None:
            return
        answer = QMessageBox.question(
            self, "Auswertung löschen", f"Die gespeicherte Auswertung '{name}' löschen?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._reports.delete_definition(self._user_id, name)
        except DomainError as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))
            return
        self._reload_saved()

    # Ausführen

    def run(self) -> None:
        name = self.saved_combo.currentData() or ""
        try:
            result = self._reports.run(self.definition(name))
        except DomainError as error:
            self._clear_result()
            self._show_message(str(error), error=True)
            return
        self._last_result = result
        self._show_result(result)
        self.pdf_button.setEnabled(True)
        self._show_message("")

    def _show_result(self, result: ReportResult) -> None:
        rows = [result.total_row, *result.rows]
        self.table.setColumnCount(len(result.columns))
        self.table.setHorizontalHeaderLabels([column.label for column in result.columns])
        self.table.setRowCount(len(rows))
        bold = QFont()
        bold.setBold(True)
        for row_index, row in enumerate(rows):
            for column_index, text in enumerate(row.cells):
                item = QTableWidgetItem(text)
                if result.columns[column_index].kind in (ColumnKind.MONEY, ColumnKind.INT):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if row.style is not RowStyle.NORMAL:
                    item.setFont(bold)
                    item.setBackground(_ROW_BACKGROUND[row.style])
                self.table.setItem(row_index, column_index, item)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.summary_label.setText(f"{result.row_count} Zeilen · {'; '.join(result.filter_lines)}")

    def _clear_result(self) -> None:
        self._last_result = None
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.summary_label.setText("")
        self.pdf_button.setEnabled(False)

    def _export_pdf(self) -> None:
        definition = self.definition(self.saved_combo.currentData() or "")
        self._exporter.export_with(
            self,
            lambda suffix: self._reports.export_pdf(
                definition, suffix=suffix, actor_id=self._user_id
            ),
        )

    def _show_message(self, text: str, *, error: bool = False) -> None:
        self.message_label.setText(text)
        self.message_label.setStyleSheet(_BAD if error else "")

    @property
    def last_result(self) -> ReportResult | None:
        return self._last_result
