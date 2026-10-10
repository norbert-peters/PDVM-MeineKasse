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
from meine_kasse.application.services.planning_service import (
    MonthPlanInput,
    PlanMonthView,
    PlanningService,
    PlanView,
)
from meine_kasse.domain.enums import PlanMode
from meine_kasse.domain.errors import DomainError, ValidationError
from meine_kasse.domain.services.planning_rules import (
    MONTHS,
    distribute_evenly,
    distribute_quarters,
)
from meine_kasse.domain.value_objects.money import format_euro, parse_euro
from meine_kasse.presentation.dialogs.quarter_amounts_dialog import QuarterAmountsDialog
from meine_kasse.presentation.labels import MONTH_NAMES, PLAN_MODE_LABELS

_PLAN_COLUMN, _MODE_COLUMN, _RESERVE_COLUMN = 1, 2, 3
_DEVIATION_COLUMN, _STATUS_COLUMN = 7, 8
_HEADERS = [
    "Monat",
    "Plan-Ansatz",
    "Art",
    "Rückstellung (Plan)",
    "Ist Soll",
    "Ist Haben",
    "Ist-Bewegung",
    "Plan − Ist",
    "Status",
]
_CLOSED_BACKGROUND = QBrush(QColor("#e6e6e6"))
_CLOSED_FOREGROUND = QBrush(QColor("#707070"))
_BAD = "color: #b00020;"
_GOOD = "color: #1b6e2d;"
_MUTED = "color: #606060;"


class PlanningDialog(QDialog):
    """Kostenstellenplanung: Haushaltsansatz, Monatswerte und Soll-/Ist-Vergleich.

    Die Höhe des Ansatzes ist bei aktiver Planung fix und ändert sich nur durch
    Ansatzumbuchung. Die Verteilung auf Monate erfolgt hier, abgeschlossene Monate sind gesperrt.
    """

    def __init__(
        self,
        planning: PlanningService,
        control: BookingControlService,
        actor_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kostenstellenplanung")
        self.resize(1120, 700)
        self._planning = planning
        self._actor_id = actor_id
        self._view: PlanView | None = None
        self._dirty = False
        self._selection: tuple[str | None, int] = (None, 0)

        self.cost_center_combo = QComboBox()
        for cost_center in planning.list_planned_cost_centers():
            self.cost_center_combo.addItem(
                f"{cost_center.number} – {cost_center.name}", cost_center.id
            )
        self.year_spin = QSpinBox()
        self.year_spin.setRange(MIN_YEAR, MAX_YEAR)
        self.year_spin.setValue(control.get().current_year)

        self.base_edit = QLineEdit()
        self.base_hint = QLabel()
        self.base_hint.setStyleSheet(_MUTED)
        self.carry_in_edit = QLineEdit()
        self.carry_out_edit = QLineEdit()
        self.transfer_label = QLabel()
        self.effective_label = QLabel()
        self.distributed_label = QLabel()
        self.undistributed_label = QLabel()
        self.movement_label = QLabel()
        self.remaining_label = QLabel()
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        self.table = QTableWidget(len(MONTHS), len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.mode_combos: dict[int, QComboBox] = {}
        for index, month in enumerate(MONTHS):
            combo = QComboBox()
            for mode, label in PLAN_MODE_LABELS.items():
                combo.addItem(label, mode.value)
            combo.currentIndexChanged.connect(lambda _index: self._mark_dirty())
            self.mode_combos[month] = combo
            self.table.setCellWidget(index, _MODE_COLUMN, combo)

        self.distribute_button = self._button("&Gleichmäßig verteilen", self._distribute_evenly)
        self.quarter_button = self._button("&Quartalsbeträge…", self._distribute_quarters)
        self.save_button = self._button("&Speichern", self._save)
        self.reset_button = self._button("&Zurücksetzen", self._reload)
        close_button = self._button("S&chließen", self._close)

        selection_row = QHBoxLayout()
        selection_row.addWidget(QLabel("Kostenstelle:"))
        selection_row.addWidget(self.cost_center_combo, 1)
        selection_row.addWidget(QLabel("Jahr:"))
        selection_row.addWidget(self.year_spin)

        summary = QFormLayout()
        summary.addRow("Haushaltsansatz (Basis):", self.base_edit)
        summary.addRow("", self.base_hint)
        summary.addRow("Ansatzumbuchungen:", self.transfer_label)
        summary.addRow("Jahresansatz (wirksam):", self.effective_label)
        summary.addRow("Auf Monate verteilt:", self.distributed_label)
        summary.addRow("Noch nicht verteilt:", self.undistributed_label)
        summary.addRow("Ist-Bewegung (Soll − Haben):", self.movement_label)
        summary.addRow("Haushaltsrest:", self.remaining_label)
        summary.addRow("Übertrag Rückstellung Vorjahr:", self.carry_in_edit)
        summary.addRow("Übertrag Rückstellung Folgejahr:", self.carry_out_edit)

        buttons = QHBoxLayout()
        for button in (
            self.distribute_button,
            self.quarter_button,
            self.save_button,
            self.reset_button,
        ):
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
        self.table.itemChanged.connect(lambda _item: self._edited())
        for edit in (self.base_edit, self.carry_in_edit, self.carry_out_edit):
            edit.textEdited.connect(lambda _text: self._edited())

        if self.cost_center_combo.count() == 0:
            self.message_label.setText("Es gibt keine aktive Kostenstelle mit Plan.")
            self._set_enabled(False)
        else:
            self._selection = (self.cost_center_combo.currentData(), self.year_spin.value())
            self._reload()

    # Hilfsfunktionen für den Aufbau

    @staticmethod
    def _button(text: str, handler: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False: handler())
        return button

    def _set_enabled(self, enabled: bool) -> None:
        for widget in (
            self.base_edit,
            self.carry_in_edit,
            self.carry_out_edit,
            self.table,
            self.distribute_button,
            self.quarter_button,
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
            view = self._planning.get_plan_view(cost_center_id, self.year_spin.value())
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        self._view = view
        self._populate(view)
        self._dirty = False
        self._show_message("")

    def _populate(self, view: PlanView) -> None:
        self.table.blockSignals(True)
        for edit in (self.base_edit, self.carry_in_edit, self.carry_out_edit):
            edit.blockSignals(True)
        try:
            self.base_edit.setText(format_euro(view.base_budget_cents))
            self.carry_in_edit.setText(format_euro(view.reserve_carry_in_cents))
            self.carry_out_edit.setText(format_euro(view.reserve_carry_out_cents))
            for index, month in enumerate(view.months):
                self._fill_row(index, month)
        finally:
            self.table.blockSignals(False)
            for edit in (self.base_edit, self.carry_in_edit, self.carry_out_edit):
                edit.blockSignals(False)

        self.base_edit.setEnabled(view.base_editable)
        for edit in (self.carry_in_edit, self.carry_out_edit):
            edit.setEnabled(not view.year_closed)
        for button in (self.distribute_button, self.quarter_button, self.save_button):
            button.setEnabled(not view.year_closed)
        if view.year_closed:
            self.base_hint.setText(
                "Das Jahr ist abgeschlossen. Es kann nichts mehr geändert werden."
            )
        elif view.planning_enabled:
            self.base_hint.setText(
                "Bei aktiver Planung ist der Ansatz fix. Änderungen nur per Ansatzumbuchung."
            )
        else:
            self.base_hint.setText(
                "Die Planung ist nicht aktiv, der Ansatz kann noch geändert werden."
            )
        self.transfer_label.setText(format_euro(view.budget_transfer_cents))
        self.movement_label.setText(format_euro(view.movement_cents))
        self._update_summary()

    def _fill_row(self, index: int, month: PlanMonthView) -> None:
        closed = month.is_closed
        values = [
            MONTH_NAMES[month.month - 1],
            format_euro(month.plan_cents),
            None,
            format_euro(month.reserve_plan_cents),
            format_euro(month.debit_cents),
            format_euro(month.credit_cents),
            format_euro(month.movement_cents),
            format_euro(month.deviation_cents),
            "abgeschlossen (fix)" if closed else "offen (frei)",
        ]
        editable = {_PLAN_COLUMN, _RESERVE_COLUMN} if not closed else set()
        for column, value in enumerate(values):
            if value is None:
                continue
            item = QTableWidgetItem(value)
            if column in (1, 3, 4, 5, 6, 7):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if column not in editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if closed:
                item.setBackground(_CLOSED_BACKGROUND)
                item.setForeground(_CLOSED_FOREGROUND)
            self.table.setItem(index, column, item)
        combo = self.mode_combos[month.month]
        combo.blockSignals(True)
        combo.setCurrentIndex(combo.findData(month.plan_mode.value))
        combo.blockSignals(False)
        combo.setEnabled(not closed)

    # Eingaben lesen und Zusammenfassung

    def _amount(self, text: str) -> int:
        return parse_euro(text) if text.strip() else 0

    def _cell_amount(self, row: int, column: int) -> int:
        item = self.table.item(row, column)
        return self._amount(item.text()) if item is not None else 0

    def _collect(self) -> tuple[int, int, int, list[MonthPlanInput]]:
        months: list[MonthPlanInput] = []
        for index, month in enumerate(MONTHS):
            try:
                plan = self._cell_amount(index, _PLAN_COLUMN)
                reserve = self._cell_amount(index, _RESERVE_COLUMN)
            except ValidationError as error:
                raise ValidationError(f"{MONTH_NAMES[index]}: {error}") from error
            mode = PlanMode(self.mode_combos[month].currentData())
            months.append(MonthPlanInput(month, plan, reserve, mode))
        return (
            self._amount(self.base_edit.text()),
            self._amount(self.carry_in_edit.text()),
            self._amount(self.carry_out_edit.text()),
            months,
        )

    def _edited(self) -> None:
        self._mark_dirty()
        self._update_summary()

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _update_summary(self) -> None:
        view = self._view
        if view is None:
            return
        try:
            base, _carry_in, _carry_out, months = self._collect()
        except ValidationError as error:
            self._show_message(str(error), bad=True)
            return
        effective = base + view.budget_transfer_cents
        distributed = sum(month.plan_cents for month in months)
        undistributed = effective - distributed
        self.effective_label.setText(format_euro(effective))
        self.distributed_label.setText(format_euro(distributed))
        self.undistributed_label.setText(format_euro(undistributed))
        self.undistributed_label.setStyleSheet(_BAD if undistributed < 0 else "")
        self.remaining_label.setText(format_euro(effective - view.movement_cents))
        self.table.blockSignals(True)
        for index, month in enumerate(months):
            item = self.table.item(index, _DEVIATION_COLUMN)
            if item is not None:
                item.setText(format_euro(month.plan_cents - view.months[index].movement_cents))
        self.table.blockSignals(False)
        if undistributed < 0:
            self._show_message(
                f"Die Monatsplanung übersteigt den Jahresansatz um {format_euro(-undistributed)}.",
                bad=True,
            )
        elif self.message_label.styleSheet() == _BAD:
            self._show_message("")

    def _show_message(self, text: str, *, bad: bool = False, good: bool = False) -> None:
        self.message_label.setText(text)
        self.message_label.setStyleSheet(_BAD if bad else _GOOD if good else "")

    # Aktionen

    def _set_plan_cell(self, row: int, cents: int, mode: PlanMode) -> None:
        item = self.table.item(row, _PLAN_COLUMN)
        if item is not None:
            item.setText(format_euro(cents))
        combo = self.mode_combos[row + 1]
        combo.blockSignals(True)
        combo.setCurrentIndex(combo.findData(mode.value))
        combo.blockSignals(False)

    def _open_months(self) -> list[int]:
        assert self._view is not None
        return [month.month for month in self._view.months if not month.is_closed]

    def _distribute_evenly(self) -> None:
        view = self._view
        if view is None:
            return
        try:
            base, _in, _out, months = self._collect()
            open_months = self._open_months()
            closed_total = sum(m.plan_cents for m in months if m.month not in open_months)
            total = base + view.budget_transfer_cents - closed_total
            shares = distribute_evenly(total, open_months)
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        for month, cents in shares.items():
            self._set_plan_cell(month - 1, cents, PlanMode.MONTHLY)
        self._mark_dirty()
        self._update_summary()

    def _distribute_quarters(self) -> None:
        if self._view is None:
            return
        dialog = QuarterAmountsDialog(self)
        if not dialog.exec():
            return
        try:
            shares = distribute_quarters(dialog.amounts, set(self._open_months()))
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        for month, cents in shares.items():
            self._set_plan_cell(month - 1, cents, PlanMode.QUARTERLY if cents else PlanMode.MONTHLY)
        self._mark_dirty()
        self._update_summary()

    def _save(self) -> None:
        cost_center_id = self.cost_center_combo.currentData()
        if cost_center_id is None:
            return
        try:
            base, carry_in, carry_out, months = self._collect()
            self._planning.save_plan(
                cost_center_id,
                self.year_spin.value(),
                base_budget_cents=base,
                reserve_carry_in_cents=carry_in,
                reserve_carry_out_cents=carry_out,
                months=months,
                actor_id=self._actor_id,
            )
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        self._reload()
        self._show_message("Die Planung wurde gespeichert.", good=True)

    # Wechsel von Kostenstelle oder Jahr, Schließen

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Ungespeicherte Änderungen",
            "Die Änderungen an der Planung wurden noch nicht gespeichert. Verwerfen?",
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
