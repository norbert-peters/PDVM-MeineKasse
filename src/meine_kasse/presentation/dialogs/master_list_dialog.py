from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.domain.errors import DomainError

_INACTIVE_COLOR = QColor("#808080")


@dataclass(frozen=True, slots=True)
class ListRow:
    id: str
    cells: Sequence[str]
    active: bool


class MasterListDialog(QDialog):
    """Basis für Listen mit Neu, Bearbeiten und (De-)Aktivieren. Stammdaten werden nie gelöscht."""

    def __init__(self, title: str, columns: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(860, 460)

        self.table = QTableWidget(0, len(columns) + 1)
        self.table.setHorizontalHeaderLabels([*columns, "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda _item: self._edit_selected())

        self.show_inactive = QCheckBox("Inaktive anzeigen")
        self.show_inactive.toggled.connect(lambda _checked: self.refresh())

        self.new_button = QPushButton("&Neu…")
        self.new_button.clicked.connect(self._new)
        self.edit_button = QPushButton("&Bearbeiten…")
        self.edit_button.clicked.connect(self._edit_selected)
        self.toggle_button = QPushButton("&Deaktivieren")
        self.toggle_button.clicked.connect(self._toggle_active)
        close_button = QPushButton("&Schließen")
        close_button.clicked.connect(self.accept)

        self._selection_buttons: list[QPushButton] = [self.edit_button, self.toggle_button]
        self.button_row = QHBoxLayout()
        for button in (self.new_button, self.edit_button, self.toggle_button):
            self.button_row.addWidget(button)
        self.button_row.addStretch()
        self.button_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.show_inactive)
        layout.addWidget(self.table)
        layout.addLayout(self.button_row)

    # Von Unterklassen bereitzustellen

    def load_rows(self, include_inactive: bool) -> Sequence[ListRow]:
        raise NotImplementedError

    def open_editor(self, entity_id: str | None) -> bool:
        """Öffnet den Bearbeitungsdialog. Gibt `True` zurück, wenn gespeichert wurde."""
        raise NotImplementedError

    def apply_active(self, entity_id: str, active: bool) -> None:
        raise NotImplementedError

    # Gemeinsame Funktionen

    def add_action(self, label: str, handler: Callable[[str], None]) -> QPushButton:
        """Fügt eine Schaltfläche hinzu, die auf die markierte Zeile wirkt."""
        button = QPushButton(label)
        button.clicked.connect(lambda: self._run_for_selected(handler))
        self.button_row.insertWidget(self.button_row.count() - 2, button)
        self._selection_buttons.append(button)
        button.setEnabled(False)
        return button

    def selected_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None
        item = self.table.item(row, 0)
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def refresh(self) -> None:
        keep = self.selected_id()
        try:
            rows = self.load_rows(self.show_inactive.isChecked())
        except DomainError as error:
            self._warn(str(error))
            return
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = [*row.cells, "Aktiv" if row.active else "Inaktiv"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.id)
                if not row.active:
                    item.setForeground(QBrush(_INACTIVE_COLOR))
                self.table.setItem(index, column, item)
            if row.id == keep:
                self.table.selectRow(index)
        self._update_buttons()

    def _update_buttons(self) -> None:
        selected = self.selected_id()
        for button in self._selection_buttons:
            button.setEnabled(selected is not None)
        if selected is None:
            self.toggle_button.setText("&Deaktivieren")
            return
        status_item = self.table.item(self.table.currentRow(), self.table.columnCount() - 1)
        is_active = status_item is None or status_item.text() == "Aktiv"
        self.toggle_button.setText("&Deaktivieren" if is_active else "&Aktivieren")

    def _new(self) -> None:
        if self.open_editor(None):
            self.refresh()

    def _edit_selected(self) -> None:
        selected = self.selected_id()
        if selected is not None and self.open_editor(selected):
            self.refresh()

    def _toggle_active(self) -> None:
        selected = self.selected_id()
        if selected is None:
            return
        status_item = self.table.item(self.table.currentRow(), self.table.columnCount() - 1)
        make_active = status_item is not None and status_item.text() != "Aktiv"
        try:
            self.apply_active(selected, make_active)
        except DomainError as error:
            self._warn(str(error))
            return
        self.refresh()

    def _run_for_selected(self, handler: Callable[[str], None]) -> None:
        selected = self.selected_id()
        if selected is None:
            return
        try:
            handler(selected)
        except DomainError as error:
            self._warn(str(error))
            return
        self.refresh()

    def _warn(self, message: str) -> None:
        QMessageBox.warning(self, self.windowTitle(), message)
