from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
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
    ReservePreview,
)
from meine_kasse.domain.enums import PlanMode
from meine_kasse.domain.errors import DomainError, ValidationError
from meine_kasse.domain.services.planning_rules import MONTHS, distribute_evenly
from meine_kasse.domain.value_objects.money import format_euro, parse_euro
from meine_kasse.presentation.labels import MONTH_NAMES

_PLAN_COLUMN, _RESERVE_COLUMN, _KIND_COLUMN = 1, 2, 3
_DEVIATION_COLUMN, _RELEASE_COLUMN, _BALANCE_COLUMN, _STATUS_COLUMN = 7, 8, 9, 10
_HEADERS = [
    "Monat",
    "Plan-Ansatz",
    "Rückstellung (Zuführung)",
    "Zuführung",
    "Ist Soll",
    "Ist Haben",
    "Ist-Bewegung",
    "Plan − Ist",
    "Rückstellung (Entlastung)",
    "Rückstellung (Bestand)",
    "Status",
]
_MONEY_COLUMNS = (1, 2, 4, 5, 6, 7, 8, 9)
_CLOSED_BACKGROUND = QBrush(QColor("#e6e6e6"))
_CLOSED_FOREGROUND = QBrush(QColor("#707070"))
_MANUAL_BACKGROUND = QBrush(QColor("#fff4cc"))
_BAD = "color: #b00020;"
_GOOD = "color: #1b6e2d;"
_WARN = "color: #8a5a00;"
_MUTED = "color: #606060;"


class PlanningDialog(QDialog):
    """Kostenstellenplanung: Haushaltsansatz, Monatswerte, Rückstellung und Soll-/Ist-Vergleich.

    Die Höhe des Ansatzes ist bei aktiver Planung fix und ändert sich nur durch
    Ansatzumbuchung. Die Verteilung auf Monate erfolgt hier, abgeschlossene Monate sind gesperrt.
    Die Zuführungen zur Rückstellung werden maschinell berechnet; ein von Hand geänderter Monat
    bleibt erhalten (leeres Feld = wieder maschinell).
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
        self.resize(1240, 720)
        self._planning = planning
        self._actor_id = actor_id
        self._view: PlanView | None = None
        self._dirty = False
        self._busy = False
        self._selection: tuple[str | None, int] = (None, 0)
        self._manual: set[int] = set()
        self._modes: dict[int, PlanMode] = {}
        self._notices: tuple[str, ...] = ()
        self._error = ""
        self._info = ""
        self._over_text = ""
        self._carry_auto = False

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
        self.carry_in_auto_button = self._button("Vortrag &automatisch", self._carry_in_to_auto)
        self.carry_in_auto_button.setAutoDefault(False)
        self.carry_in_auto_button.setToolTip(
            "Nimmt die Überschreibung zurück: Der Vortrag folgt wieder dem Vorjahr."
        )
        self.carry_in_hint = QLabel()
        self.carry_in_hint.setStyleSheet(_MUTED)
        self.carry_out_label = QLabel()
        self.transfer_label = QLabel()
        self.effective_label = QLabel()
        self.distributed_label = QLabel()
        self.undistributed_label = QLabel()
        self.reserve_total_label = QLabel()
        self.movement_label = QLabel()
        self.remaining_label = QLabel()
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        self.table = QTableWidget(len(MONTHS), len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.distribute_button = self._button("&Gleichmäßig verteilen", self._distribute_evenly)
        self.reserve_button = self._button("&Rückstellung maschinell", self._reset_reserve)
        self.reserve_button.setToolTip(
            "Verwirft manuelle Rückstellungswerte der offenen Monate und verteilt sie gleichmäßig "
            "auf die offenen Monate. Geplante Zahlungen entlasten die Rückstellung im Plan."
        )
        self.target_button = self._button(
            "Rückstellung auf &Zahlungsziel", self._reserve_to_payment_targets
        )
        self.target_button.setToolTip(
            "Erhöht die Zuführungen vor den geplanten Zahlungen, sodass jede Zahlung zum "
            "Zahlungsmonat gedeckt ist. Die Werte werden als manuell übernommen."
        )
        self.save_button = self._button("&Speichern", self._save)
        self.save_button.setDefault(True)
        self.reset_button = self._button("&Zurücksetzen", self._reload)
        close_button = self._button("S&chließen", self._close)
        for button in (
            self.distribute_button,
            self.reserve_button,
            self.target_button,
            self.reset_button,
            close_button,
        ):
            button.setAutoDefault(False)

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
        carry_in_row = QHBoxLayout()
        carry_in_row.addWidget(self.carry_in_edit, 1)
        carry_in_row.addWidget(self.carry_in_auto_button)
        summary.addRow("Rückstellung Vortrag (Vorjahr):", carry_in_row)
        summary.addRow("", self.carry_in_hint)
        summary.addRow("Rückstellung zugeführt (Jahr):", self.reserve_total_label)
        summary.addRow("Rückstellung Vortrag (Folgejahr):", self.carry_out_label)

        buttons = QHBoxLayout()
        for button in (
            self.save_button,
            self.reset_button,
            self.distribute_button,
            self.reserve_button,
            self.target_button,
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
        self.table.itemChanged.connect(self._on_item_changed)
        self.base_edit.textEdited.connect(lambda _text: self._on_header_edited())
        self.carry_in_edit.textEdited.connect(lambda _text: self._on_carry_in_edited())

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
            self.carry_in_auto_button,
            self.table,
            self.distribute_button,
            self.reserve_button,
            self.target_button,
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
        self._manual = {m.month for m in view.months if m.reserve_is_manual}
        self._modes = {m.month: m.plan_mode for m in view.months}
        self._notices = view.reserve_notices
        self._carry_auto = False
        self._error = self._info = ""
        self._populate(view)
        self._dirty = False

    def _populate(self, view: PlanView) -> None:
        self._busy = True
        try:
            self.base_edit.setText(format_euro(view.base_budget_cents))
            self.carry_in_edit.setText(format_euro(view.reserve_carry_in_cents))
            self.carry_out_label.setText(format_euro(view.reserve_carry_out_cents))
            for index, month in enumerate(view.months):
                self._fill_row(index, month)
        finally:
            self._busy = False

        self.base_edit.setEnabled(view.base_editable)
        self.carry_in_edit.setEnabled(view.reserve_carry_in_editable)
        self.carry_in_auto_button.setEnabled(
            view.reserve_carry_in_editable and view.reserve_carry_in_derivable
        )
        for button in (
            self.distribute_button,
            self.reserve_button,
            self.target_button,
            self.save_button,
        ):
            button.setEnabled(not view.year_closed)
        if view.year_closed:
            self.base_hint.setText(
                "Das Jahr ist abgeschlossen. Es kann nichts mehr geändert werden."
            )
        elif view.planning_enabled and not view.is_future_year:
            self.base_hint.setText(
                "Bei aktiver Planung ist der Ansatz fix. Änderungen nur per Ansatzumbuchung."
            )
        elif view.planning_enabled:
            self.base_hint.setText(
                "Folgejahr des Buchungsjahres: Der Ansatz kann vorab geplant werden."
            )
        else:
            self.base_hint.setText(
                "Die Planung ist nicht aktiv, der Ansatz kann noch geändert werden."
            )
        if not view.reserve_carry_in_derivable:
            if view.reserve_carry_in_editable:
                self.carry_in_hint.setText("Kein Vorjahresplan: Der Vortrag wird von Hand erfasst.")
            else:
                self.carry_in_hint.setText("Der Vortrag ist fix (Januar abgeschlossen).")
        elif not view.reserve_carry_in_editable:
            self.carry_in_hint.setText(
                "Der Vortrag ist fix (Januar abgeschlossen)."
                if view.reserve_carry_in_manual
                else "Der Vortrag wird aus dem Vorjahr übernommen."
            )
        elif view.reserve_carry_in_manual:
            self.carry_in_hint.setText(
                "Der Vortrag wurde von Hand überschrieben und ist bis zum Abschluss des Januars "
                "änderbar. Mit »Vortrag automatisch« folgt er wieder dem Vorjahr."
            )
        else:
            self.carry_in_hint.setText(
                "Prognose aus dem Vorjahr. Sie kann bis zum Abschluss des Januars überschrieben "
                "werden und ist danach fix."
            )
        self.transfer_label.setText(format_euro(view.budget_transfer_cents))
        self.movement_label.setText(format_euro(view.movement_cents))
        self.reserve_total_label.setText(
            format_euro(sum(m.reserve_plan_cents for m in view.months))
        )
        self._update_summary()

    def _fill_row(self, index: int, month: PlanMonthView) -> None:
        closed = month.is_closed
        manual = month.month in self._manual
        values = [
            MONTH_NAMES[month.month - 1],
            format_euro(month.plan_cents),
            format_euro(month.reserve_plan_cents),
            "manuell" if manual else "maschinell",
            format_euro(month.debit_cents),
            format_euro(month.credit_cents),
            format_euro(month.movement_cents),
            format_euro(month.deviation_cents),
            format_euro(month.reserve_release_cents),
            format_euro(month.reserve_balance_cents),
            "abgeschlossen (fix)" if closed else "offen (frei)",
        ]
        editable = {_PLAN_COLUMN, _RESERVE_COLUMN} if not closed else set()
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column in _MONEY_COLUMNS:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if column not in editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if closed:
                item.setBackground(_CLOSED_BACKGROUND)
                item.setForeground(_CLOSED_FOREGROUND)
            elif manual and column in (_RESERVE_COLUMN, _KIND_COLUMN):
                item.setBackground(_MANUAL_BACKGROUND)
                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
            self.table.setItem(index, column, item)

    # Eingaben lesen

    @staticmethod
    def _amount(text: str) -> int:
        return parse_euro(text) if text.strip() else 0

    def _cell_text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text() if item is not None else ""

    def _collect(self) -> tuple[int, int, list[MonthPlanInput]]:
        months: list[MonthPlanInput] = []
        for index, month in enumerate(MONTHS):
            try:
                plan = self._amount(self._cell_text(index, _PLAN_COLUMN))
                reserve = (
                    self._amount(self._cell_text(index, _RESERVE_COLUMN))
                    if month in self._manual
                    else None
                )
            except ValidationError as error:
                raise ValidationError(f"{MONTH_NAMES[index]}: {error}") from error
            months.append(
                MonthPlanInput(month, plan, reserve, self._modes.get(month, PlanMode.MONTHLY))
            )
        return (
            self._amount(self.base_edit.text()),
            self._amount(self.carry_in_edit.text()),
            months,
        )

    # Reaktion auf Eingaben

    def _on_header_edited(self) -> None:
        self._mark_dirty()
        self._recompute()

    def _on_carry_in_edited(self) -> None:
        self._carry_auto = False
        self._on_header_edited()

    def _carry_in_to_auto(self) -> None:
        self._carry_auto = True
        self._on_header_edited()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._busy:
            return
        column, row = item.column(), item.row()
        month = row + 1
        if column == _RESERVE_COLUMN:
            if item.text().strip():
                self._manual.add(month)
            else:
                self._manual.discard(month)
        elif column != _PLAN_COLUMN:
            return
        self._mark_dirty()
        self._recompute()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._info = ""

    def _recompute(self) -> None:
        """Berechnet die maschinelle Rückstellung für die aktuellen Eingaben neu."""
        view = self._view
        cost_center_id = self.cost_center_combo.currentData()
        if view is None or cost_center_id is None:
            return
        try:
            base, carry_in, months = self._collect()
            preview = self._planning.preview_reserve(
                cost_center_id,
                self.year_spin.value(),
                base_budget_cents=base,
                carry_in_cents=carry_in,
                months=months,
                carry_in_automatic=self._carry_auto,
            )
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        self._error = ""
        self._apply_preview(preview)
        self._update_summary()

    def _apply_preview(self, preview: ReservePreview) -> None:
        view = self._view
        assert view is not None
        self._busy = True
        try:
            for index, month in enumerate(MONTHS):
                manual = month in self._manual
                closed = view.months[index].is_closed
                values = {
                    _RESERVE_COLUMN: format_euro(preview.reserve_plan[month]),
                    _KIND_COLUMN: "manuell" if manual else "maschinell",
                    _RELEASE_COLUMN: format_euro(preview.release[month]),
                    _BALANCE_COLUMN: format_euro(preview.balance[month]),
                }
                for column, text in values.items():
                    item = self.table.item(index, column)
                    if item is None:
                        continue
                    if column == _RESERVE_COLUMN and manual and not closed:
                        continue  # Die Eingabe des Anwenders bleibt unverändert stehen.
                    item.setText(text)
                self._style_reserve_cells(index, manual and not closed)
            self.carry_out_label.setText(format_euro(preview.carry_out_cents))
            if not self.carry_in_edit.isEnabled() or self._carry_auto:
                self.carry_in_edit.setText(format_euro(preview.carry_in_cents))
        finally:
            self._busy = False
        self._notices = preview.notices
        self.reserve_total_label.setText(format_euro(sum(preview.reserve_plan.values())))
        self._render_message()

    def _style_reserve_cells(self, index: int, manual: bool) -> None:
        for column in (_RESERVE_COLUMN, _KIND_COLUMN):
            item = self.table.item(index, column)
            if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                continue
            font = QFont(item.font())
            font.setBold(manual)
            item.setFont(font)
            if self._view is not None and self._view.months[index].is_closed:
                continue
            item.setBackground(_MANUAL_BACKGROUND if manual else QBrush())

    def _update_summary(self) -> None:
        view = self._view
        if view is None:
            return
        try:
            base, _carry_in, months = self._collect()
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
        self._busy = True
        try:
            for index, month in enumerate(months):
                item = self.table.item(index, _DEVIATION_COLUMN)
                if item is not None:
                    item.setText(format_euro(month.plan_cents - view.months[index].movement_cents))
        finally:
            self._busy = False
        self._over_text = (
            f"Die Monatsplanung übersteigt den Jahresansatz um {format_euro(-undistributed)}."
            if undistributed < 0
            else ""
        )
        self._render_message()

    # Meldungen

    def _show_message(self, text: str, *, bad: bool = False, good: bool = False) -> None:
        """Setzt Fehler bzw. Erfolgsmeldung. Hinweise zur Rückstellung werden angehängt."""
        self._error = text if bad else ""
        self._info = text if good else ""
        self._render_message()

    def _render_message(self) -> None:
        """Rangfolge: Fehler, Überverteilung, Erfolg mit Hinweisen, Hinweise der Rückstellung."""
        notices = "\n".join(self._notices)
        if self._error:
            text, style = self._error, _BAD
        elif self._over_text:
            text, style = self._over_text, _BAD
        elif self._info:
            text, style = self._info + (f"\n{notices}" if notices else ""), _GOOD
        elif notices:
            text, style = notices, _WARN
        else:
            text, style = "", ""
        self.message_label.setText(text)
        self.message_label.setStyleSheet(style)

    # Aktionen

    def _set_plan_cell(self, row: int, cents: int) -> None:
        item = self.table.item(row, _PLAN_COLUMN)
        if item is not None:
            item.setText(format_euro(cents))

    def _open_months(self) -> list[int]:
        assert self._view is not None
        return [month.month for month in self._view.months if not month.is_closed]

    def _distribute_evenly(self) -> None:
        view = self._view
        if view is None:
            return
        try:
            base, _carry_in, months = self._collect()
            open_months = self._open_months()
            closed_total = sum(m.plan_cents for m in months if m.month not in open_months)
            total = base + view.budget_transfer_cents - closed_total
            shares = distribute_evenly(total, open_months)
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        self._busy = True
        try:
            for month, cents in shares.items():
                self._set_plan_cell(month - 1, cents)
        finally:
            self._busy = False
        self._mark_dirty()
        self._recompute()

    def _reset_reserve(self) -> None:
        if self._view is None:
            return
        self._manual -= set(self._open_months())
        self._mark_dirty()
        self._recompute()

    def _reserve_to_payment_targets(self) -> None:
        """Richtet die Zuführungen der offenen Monate auf die geplanten Zahlungen aus.

        Die Werte werden als manuelle Zuführung übernommen und bleiben so bei weiteren Eingaben
        stehen. Ein leeres Feld macht den Monat wieder maschinell (gleichmäßig).
        """
        view = self._view
        cost_center_id = self.cost_center_combo.currentData()
        if view is None or cost_center_id is None:
            return
        open_months = self._open_months()
        self._manual -= set(open_months)
        try:
            base, carry_in, months = self._collect()
            year = self.year_spin.value()
            even = self._planning.preview_reserve(
                cost_center_id,
                year,
                base_budget_cents=base,
                carry_in_cents=carry_in,
                months=months,
                carry_in_automatic=self._carry_auto,
            )
            target = self._planning.preview_reserve(
                cost_center_id,
                year,
                base_budget_cents=base,
                carry_in_cents=carry_in,
                months=months,
                to_payment_targets=True,
                carry_in_automatic=self._carry_auto,
            )
        except DomainError as error:
            self._show_message(str(error), bad=True)
            return
        if all(target.reserve_plan[m] == even.reserve_plan[m] for m in open_months):
            self._mark_dirty()
            self._recompute()
            self._show_message(
                "Die gleichmäßige Rückstellung deckt die geplanten Zahlungen bereits.", good=True
            )
            return
        self._busy = True
        try:
            for month in open_months:
                item = self.table.item(month - 1, _RESERVE_COLUMN)
                if item is not None:
                    item.setText(format_euro(target.reserve_plan[month]))
        finally:
            self._busy = False
        self._manual |= set(open_months)
        self._mark_dirty()
        self._recompute()

    def _save(self) -> None:
        cost_center_id = self.cost_center_combo.currentData()
        if cost_center_id is None:
            return
        try:
            base, carry_in, months = self._collect()
            self._planning.save_plan(
                cost_center_id,
                self.year_spin.value(),
                base_budget_cents=base,
                reserve_carry_in_cents=carry_in,
                months=months,
                actor_id=self._actor_id,
                carry_in_automatic=self._carry_auto,
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
