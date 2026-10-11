from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.application.services.booking_control_service import (
    MAX_YEAR,
    MIN_YEAR,
    BookingControlService,
)
from meine_kasse.application.services.opening_balance_service import (
    OpeningBalanceRow,
    OpeningBalanceService,
)
from meine_kasse.domain.errors import DomainError
from meine_kasse.domain.services.opening_rules import OpeningSource, OpeningState
from meine_kasse.domain.value_objects.money import format_euro, parse_euro

_OPENING_COLUMN = 1
_SOURCE_LABELS = {
    OpeningSource.MANUAL: "manuell erfasst",
    OpeningSource.CARRIED: "aus Vorjahr übernommen",
    OpeningSource.NONE: "kein Vortrag",
}
_LOCKED_BACKGROUND = QBrush(QColor("#e6e6e6"))
_LOCKED_FOREGROUND = QBrush(QColor("#707070"))
_EDITABLE_BACKGROUND = QBrush(QColor("#fff8dc"))
_BAD = "color: #b00020;"
_GOOD = "color: #1b6e2d;"


class OpeningBalancesDialog(QDialog):
    """Anfangssalden (Vorträge) der Konten zum 01.01. eines Jahres.

    Ein Vortrag ist nur editierbar, wenn das Konto noch kein Vorjahr hat und der Januar des
    Jahres nicht abgeschlossen ist. Sonst wird er aus dem Vorjahr abgeleitet bzw. ist gesperrt.
    """

    def __init__(
        self,
        service: OpeningBalanceService,
        control: BookingControlService,
        actor_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kontenanfangssalden")
        self.resize(980, 460)
        self._service = service
        self._actor_id = actor_id
        self._rows: list[OpeningBalanceRow] = []
        self._original: dict[str, str] = {}
        self._year = control.get().current_year

        self.year_spin = QSpinBox()
        self.year_spin.setRange(MIN_YEAR, MAX_YEAR)
        self.year_spin.setValue(self._year)
        self.year_spin.valueChanged.connect(lambda _value: self._on_year_changed())

        self.table = QTableWidget(0, 6)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        hint = QLabel(
            "Der Anfangssaldo wird zum 01.01. erfasst. Er ist editierbar, solange das Konto "
            "kein Vorjahr hat und der Januar nicht abgeschlossen ist. Ein leeres Feld entfernt "
            "den Vortrag. Salden dürfen negativ sein."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #606060;")

        self.save_button = self._button("&Speichern", self._save)
        self.reset_button = self._button("&Zurücksetzen", self._reload)
        close_button = self._button("S&chließen", self._close)

        top = QHBoxLayout()
        top.addWidget(QLabel("Jahr:"))
        top.addWidget(self.year_spin)
        top.addStretch()
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.reset_button)
        buttons.addStretch()
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.message_label)
        layout.addLayout(buttons)
        self._reload()

    @staticmethod
    def _button(text: str, handler: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False: handler())
        return button

    def _reload(self) -> None:
        year = self.year_spin.value()
        try:
            rows = list(self._service.get_overview(year))
        except DomainError as error:
            self._show(str(error), bad=True)
            return
        self._year = year
        self._rows = rows
        self._original = {}
        self.table.setHorizontalHeaderLabels(
            [
                "Konto",
                f"Anfangssaldo 01.01.{year}",
                "Herkunft",
                f"Bewegung {year}",
                "Saldo (bisher)",
                "Status",
            ]
        )
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self._fill_row(index, row)
        self._show("")

    def _fill_row(self, index: int, row: OpeningBalanceRow) -> None:
        if row.editable:
            opening_text = (
                "" if row.source is OpeningSource.NONE else format_euro(row.opening_cents)
            )
            self._original[row.account_id] = opening_text
        else:
            opening_text = format_euro(row.opening_cents)
        name = row.label if row.is_active else f"{row.label} (inaktiv)"
        values = [
            name,
            opening_text,
            _SOURCE_LABELS[row.source],
            format_euro(row.movement_cents),
            format_euro(row.balance_cents),
            row.editability.message,
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, row.account_id)
            if column in (1, 3, 4):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            editable_cell = column == _OPENING_COLUMN and row.editable
            if not editable_cell:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if editable_cell:
                item.setBackground(_EDITABLE_BACKGROUND)
            elif row.editability.state is not OpeningState.EDITABLE:
                item.setBackground(_LOCKED_BACKGROUND)
                item.setForeground(_LOCKED_FOREGROUND)
            self.table.setItem(index, column, item)

    def _show(self, text: str, *, bad: bool = False, good: bool = False) -> None:
        self.message_label.setText(text)
        self.message_label.setStyleSheet(_BAD if bad else _GOOD if good else "")

    # Änderungen erkennen und speichern

    def _changed_rows(self) -> list[tuple[OpeningBalanceRow, str]]:
        changed = []
        for index, row in enumerate(self._rows):
            if not row.editable:
                continue
            item = self.table.item(index, _OPENING_COLUMN)
            text = item.text().strip() if item is not None else ""
            if text != self._original.get(row.account_id, "").strip():
                changed.append((row, text))
        return changed

    def has_changes(self) -> bool:
        return bool(self._changed_rows())

    def _save(self) -> None:
        errors: list[str] = []
        saved = 0
        for row, text in self._changed_rows():
            try:
                if text:
                    self._service.set_opening_balance(
                        row.account_id, self._year, parse_euro(text), actor_id=self._actor_id
                    )
                else:
                    self._service.clear_opening_balance(
                        row.account_id, self._year, actor_id=self._actor_id
                    )
                saved += 1
            except DomainError as error:
                errors.append(f"{row.label}: {error}")
        self._reload()
        if errors:
            self._show("\n".join(errors), bad=True)
        elif saved:
            self._show(f"{saved} Anfangssaldo/-salden gespeichert.", good=True)

    # Jahreswechsel und Schließen

    def _confirm_discard(self) -> bool:
        if not self.has_changes():
            return True
        answer = QMessageBox.question(
            self,
            "Ungespeicherte Änderungen",
            "Die Änderungen an den Anfangssalden wurden noch nicht gespeichert. Verwerfen?",
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_year_changed(self) -> None:
        if not self._confirm_discard():
            self.year_spin.blockSignals(True)
            self.year_spin.setValue(self._year)
            self.year_spin.blockSignals(False)
            return
        self._reload()

    def _close(self) -> None:
        if self._confirm_discard():
            self.accept()
