from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
from meine_kasse.application.services.income_planning import (
    IncomeMonthInput,
    IncomeMonthView,
    IncomeView,
)
from meine_kasse.application.services.planning_service import PlanningService
from meine_kasse.domain.errors import DomainError, ValidationError
from meine_kasse.domain.services.planning_rules import MONTHS, distribute_evenly
from meine_kasse.domain.value_objects.money import format_euro, parse_euro
from meine_kasse.presentation.labels import INCOME_MODE_LABELS, MONTH_NAMES

_PLAN_COLUMN, _DEVIATION_COLUMN = 1, 5
_HEADERS = [
    "Monat",
    "Erwartet (Plan)",
    "Ist Soll",
    "Ist Haben",
    "Ist-Einnahme",
    "Ist − Plan",
    "Status",
]
_MONEY_COLUMNS = (1, 2, 3, 4, 5)
_CLOSED_BACKGROUND = QBrush(QColor("#e6e6e6"))
_CLOSED_FOREGROUND = QBrush(QColor("#707070"))
_BAD = "color: #b00020;"
_GOOD = "color: #1b6e2d;"
_MUTED = "color: #606060;"


class IncomePlanningDialog(QDialog):
    """Einnahmenplanung: erwartete Einnahme je Monat im Vergleich zur gebuchten Einnahme.

    Es gibt keinen Jahresansatz und keine Rückstellung. Die Einnahme wird erst durch eine
    Ansatzumbuchung auf eine Kostenstelle mit Plan zum Ansatz; wie viel davon umbuchbar ist,
    hängt vom Modus der Einnahmen-Kostenstelle ab (Plan oder nur Ist).
    """

    def __init__(
        self,
        planning: PlanningService,
        control: BookingControlService,
        actor_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Einnahmenplanung")
        self.resize(1000, 640)
        self._planning = planning
        self._actor_id = actor_id
        self._view: IncomeView | None = None
        self._dirty = False
        self._busy = False
        self._selection: tuple[str | None, int] = (None, 0)

        self.cost_center_combo = QComboBox()
        for cost_center in planning.list_income_cost_centers():
            self.cost_center_combo.addItem(
                f"{cost_center.number} – {cost_center.name}", cost_center.id
            )
        self.year_spin = QSpinBox()
        self.year_spin.setRange(MIN_YEAR, MAX_YEAR)
        self.year_spin.setValue(control.get().current_year)

        self.mode_label = QLabel()
        self.total_edit = QLineEdit()
        self.total_hint = QLabel("Wird mit „Gleichmäßig verteilen“ auf offene Monate verteilt.")
        self.total_hint.setStyleSheet(_MUTED)
        self.planned_label = QLabel()
        self.realized_label = QLabel()
        self.expected_label = QLabel()
        self.passed_on_label = QLabel()
        self.available_label = QLabel()
        self.free_label = QLabel()
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        self.table = QTableWidget(len(MONTHS), len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.distribute_button = self._button("&Gleichmäßig verteilen", self._distribute_evenly)
        self.save_button = self._button("&Speichern", self._save)
        self.save_button.setDefault(True)
        self.reset_button = self._button("&Zurücksetzen", self._reload)
        close_button = self._button("S&chließen", self._close)
        for button in (self.distribute_button, self.reset_button, close_button):
            button.setAutoDefault(False)

        selection_row = QHBoxLayout()
        selection_row.addWidget(QLabel("Einnahmen-Kostenstelle:"))
        selection_row.addWidget(self.cost_center_combo, 1)
        selection_row.addWidget(QLabel("Jahr:"))
        selection_row.addWidget(self.year_spin)

        summary = QFormLayout()
        summary.addRow("Verfügbarkeit:", self.mode_label)
        summary.addRow("Jahresbetrag verteilen:", self.total_edit)
        summary.addRow("", self.total_hint)
        summary.addRow("Erwartet (Plan, Jahr):", self.planned_label)
        summary.addRow("Gebucht (Ist, Jahr):", self.realized_label)
        summary.addRow("Noch erwartet:", self.expected_label)
        summary.addRow("Bereits umgebucht:", self.passed_on_label)
        summary.addRow("Verfügbar zum Umbuchen (gesamt):", self.available_label)
        summary.addRow("Noch umbuchbar:", self.free_label)

        buttons = QHBoxLayout()
        for button in (self.save_button, self.reset_button, self.distribute_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(selection_row)
        layout.addLayout(summary)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.message_label)
        layout.addLayout(buttons)

        self.cost_center_combo.currentIndexChanged.connect(lambda _index: self._on_selection())
        self.year_spin.valueChanged.connect(lambda _value: self._on_selection())
        self.table.itemChanged.connect(self._on_item_changed)

        if self.cost_center_combo.count() == 0:
            self.message_label.setText("Es gibt keine aktive Einnahmen-Kostenstelle.")
            self._set_enabled(False)
        else:
            self._selection = (self.cost_center_combo.currentData(), self.year_spin.value())
            self._reload()

    @staticmethod
    def _button(text: str, handler: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False: handler())
        return button

    def _set_enabled(self, enabled: bool) -> None:
        for widget in (
            self.total_edit,
            self.table,
            self.distribute_button,
            self.save_button,
            self.reset_button,
        ):
            widget.setEnabled(enabled)

    # Laden und Anzeigen

    def _reload(self) -> None:
        cost_center_id = self.cost_center_combo.currentData()
        if cost_center_id is None:
            return
        try:
            view = self._planning.get_income_view(cost_center_id, self.year_spin.value())
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        self._view = view
        self._busy = True
        try:
            self.total_edit.setText(format_euro(view.planned_cents))
            self.mode_label.setText(INCOME_MODE_LABELS[view.mode])
            for index, month in enumerate(view.months):
                self._fill_row(index, month)
        finally:
            self._busy = False
        for widget in (self.distribute_button, self.save_button, self.total_edit):
            widget.setEnabled(not view.year_closed)
        self._dirty = False
        self._update_summary()
        if view.year_closed:
            self._show_message("Das Jahr ist abgeschlossen. Es kann nichts mehr geändert werden.")
        else:
            self._show_message("")

    def _fill_row(self, index: int, month: IncomeMonthView) -> None:
        values = [
            MONTH_NAMES[month.month - 1],
            format_euro(month.plan_cents),
            format_euro(month.debit_cents),
            format_euro(month.credit_cents),
            format_euro(month.realized_cents),
            format_euro(month.deviation_cents),
            "abgeschlossen (fix)" if month.is_closed else "offen (frei)",
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column in _MONEY_COLUMNS:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if column != _PLAN_COLUMN or month.is_closed:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if month.is_closed:
                item.setBackground(_CLOSED_BACKGROUND)
                item.setForeground(_CLOSED_FOREGROUND)
            self.table.setItem(index, column, item)

    def _update_summary(self) -> None:
        view = self._view
        if view is None:
            return
        try:
            months = self._collect()
        except ValidationError as error:
            self._show_message(str(error), bad=True)
            return
        current = view.with_plan({item.month: item.plan_cents for item in months})
        self.planned_label.setText(format_euro(current.planned_cents))
        self.realized_label.setText(format_euro(current.realized_cents))
        self.expected_label.setText(format_euro(current.open_expected_cents))
        self.passed_on_label.setText(format_euro(current.passed_on_cents))
        self.available_label.setText(format_euro(current.available_cents))
        self.free_label.setText(format_euro(current.free_cents))
        self._busy = True
        try:
            for index, month in enumerate(current.months):
                item = self.table.item(index, _DEVIATION_COLUMN)
                if item is not None:
                    item.setText(format_euro(month.deviation_cents))
        finally:
            self._busy = False

    # Eingaben lesen

    @staticmethod
    def _amount(text: str) -> int:
        return parse_euro(text) if text.strip() else 0

    def _collect(self) -> list[IncomeMonthInput]:
        months: list[IncomeMonthInput] = []
        for index, month in enumerate(MONTHS):
            item = self.table.item(index, _PLAN_COLUMN)
            try:
                plan = self._amount(item.text() if item is not None else "")
            except ValidationError as error:
                raise ValidationError(f"{MONTH_NAMES[index]}: {error}") from error
            months.append(IncomeMonthInput(month, plan))
        return months

    # Reaktion auf Eingaben

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._busy or item.column() != _PLAN_COLUMN:
            return
        self._dirty = True
        self._show_message("")
        self._update_summary()

    # Aktionen

    def _distribute_evenly(self) -> None:
        view = self._view
        if view is None:
            return
        try:
            total = self._amount(self.total_edit.text())
            months = self._collect()
            open_months = [m.month for m in view.months if not m.is_closed]
            closed_total = sum(m.plan_cents for m in months if m.month not in open_months)
            shares = distribute_evenly(total - closed_total, open_months)
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        self._busy = True
        try:
            for month, cents in shares.items():
                item = self.table.item(month - 1, _PLAN_COLUMN)
                if item is not None:
                    item.setText(format_euro(cents))
        finally:
            self._busy = False
        self._dirty = True
        self._show_message("")
        self._update_summary()

    def _save(self) -> None:
        cost_center_id = self.cost_center_combo.currentData()
        if cost_center_id is None:
            return
        try:
            self._planning.save_income_plan(
                cost_center_id,
                self.year_spin.value(),
                months=self._collect(),
                actor_id=self._actor_id,
            )
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        self._reload()
        self._show_message("Die Einnahmenplanung wurde gespeichert.", good=True)

    def _show_message(self, text: str, *, bad: bool = False, good: bool = False) -> None:
        self.message_label.setText(text)
        self.message_label.setStyleSheet(_BAD if bad else _GOOD if good else "")

    # Wechsel von Kostenstelle oder Jahr, Schließen

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Ungespeicherte Änderungen",
            "Die Änderungen an der Einnahmenplanung wurden noch nicht gespeichert. Verwerfen?",
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_selection(self) -> None:
        if not self._confirm_discard():
            previous_id, previous_year = self._selection
            self.cost_center_combo.blockSignals(True)
            self.year_spin.blockSignals(True)
            self.cost_center_combo.setCurrentIndex(self.cost_center_combo.findData(previous_id))
            self.year_spin.setValue(previous_year)
            self.cost_center_combo.blockSignals(False)
            self.year_spin.blockSignals(False)
            return
        self._selection = (self.cost_center_combo.currentData(), self.year_spin.value())
        self._reload()

    def _close(self) -> None:
        if self._confirm_discard():
            self._dirty = False
            self.accept()

    def reject(self) -> None:
        if self._confirm_discard():
            self._dirty = False
            super().reject()
