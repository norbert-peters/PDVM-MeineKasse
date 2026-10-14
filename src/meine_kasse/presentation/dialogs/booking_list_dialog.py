from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.application.services.booking_control_service import (
    MAX_YEAR,
    MIN_YEAR,
    BookingControlService,
)
from meine_kasse.application.services.booking_service import BookingService, BookingView
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.domain.enums import BookingType, Side
from meine_kasse.domain.errors import DomainError
from meine_kasse.domain.value_objects.money import format_euro
from meine_kasse.presentation.dialogs.booking_dialog import BookingDialog
from meine_kasse.presentation.labels import BOOKING_TYPE_LABELS, MONTH_NAMES, format_date
from meine_kasse.presentation.widgets.data_table import AUTO, DataTable, SortItem, TablePreferences

_CLOSED_BACKGROUND = QBrush(QColor("#e6e6e6"))
_CLOSED_FOREGROUND = QBrush(QColor("#707070"))
_COLUMNS = [
    "Datum",
    "Art",
    "Stelle",
    "Gegenstelle",
    "Soll",
    "Haben",
    "Händler",
    "Buchungstext",
    "Status",
]
_ALL_MONTHS = 0


def _status_text(view: BookingView) -> str:
    parts = ["abgeschlossen" if view.is_closed else "offen"]
    if view.is_reversal:
        parts.append("Storno")
    if view.is_reversed:
        parts.append("storniert")
    return ", ".join(parts)


class BookingListDialog(QDialog):
    """Buchungsliste. Abgeschlossene (fixe) Monate sind grau und mit Status gekennzeichnet."""

    def __init__(
        self,
        bookings: BookingService,
        master_data: MasterDataService,
        control: BookingControlService,
        actor_id: str,
        parent: QWidget | None = None,
        *,
        preferences: TablePreferences | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Buchungen")
        self.resize(1100, 520)
        self._bookings = bookings
        self._master_data = master_data
        self._control = control
        self._actor_id = actor_id
        self._views: dict[str, BookingView] = {}

        current = control.get()
        self.status_label = QLabel()
        self.year_spin = QSpinBox()
        self.year_spin.setRange(MIN_YEAR, MAX_YEAR)
        self.year_spin.setValue(current.current_year)
        self.month_combo = QComboBox()
        self.month_combo.addItem("Alle Monate", _ALL_MONTHS)
        for number, name in enumerate(MONTH_NAMES, start=1):
            self.month_combo.addItem(name, number)
        self.month_combo.setCurrentIndex(current.current_month)
        self.year_spin.valueChanged.connect(lambda _value: self.refresh())
        self.month_combo.currentIndexChanged.connect(lambda _index: self.refresh())

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Jahr:"))
        filter_row.addWidget(self.year_spin)
        filter_row.addWidget(QLabel("Monat:"))
        filter_row.addWidget(self.month_combo)
        filter_row.addStretch()
        filter_row.addWidget(self.status_label)

        self.data_table = DataTable(_COLUMNS, table_key="bookings", preferences=preferences)
        self.table = self.data_table.table
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda _item: self._edit())

        self.new_button = self._button("&Neue Buchung…", self._new)
        self.transfer_button = self._button("&Ansatzumbuchung…", self._new_transfer)
        self.edit_button = self._button("&Bearbeiten…", self._edit)
        self.delete_button = self._button("&Löschen", self._delete)
        self.reverse_button = self._button("&Stornieren…", self._reverse)
        close_button = self._button("&Schließen", self.accept)

        buttons = QHBoxLayout()
        for button in (
            self.new_button,
            self.transfer_button,
            self.edit_button,
            self.delete_button,
            self.reverse_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(filter_row)
        layout.addWidget(self.data_table)
        layout.addLayout(buttons)
        self.refresh()

    def _button(self, text: str, handler: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False: handler())
        return button

    # Daten

    def selected_id(self) -> str | None:
        return self.data_table.selected_id()

    def refresh(self) -> None:
        keep = self.selected_id()
        month = self.month_combo.currentData()
        try:
            views = self._bookings.list_bookings(
                year=self.year_spin.value(), month=None if month == _ALL_MONTHS else month
            )
            control = self._control.get()
        except DomainError as error:
            self._warn(str(error))
            return
        planning = "aktiv" if control.planning_enabled else "nicht aktiv"
        self.status_label.setText(
            f"Aktueller Buchungsmonat: {control.current_month:02d}/{control.current_year} · "
            f"Planung {planning}"
        )
        self._views = {view.id: view for view in views}
        self.table.setRowCount(len(views))
        for row, view in enumerate(views):
            is_debit = view.entry_side is Side.DEBIT
            is_credit = view.entry_side is Side.CREDIT
            amount_text = format_euro(view.amount_cents)
            debit = (amount_text, view.amount_cents) if is_debit else ("", None)
            credit = (amount_text, view.amount_cents) if is_credit else ("", None)
            cells: list[tuple[str, object]] = [
                (format_date(view.booking_date), view.booking_date.toordinal()),
                (BOOKING_TYPE_LABELS[view.booking_type], AUTO),
                (view.leading_label, AUTO),
                (view.second_label, AUTO),
                debit,
                credit,
                (view.merchant, AUTO),
                (view.booking_text, AUTO),
                (_status_text(view), AUTO),
            ]
            for column, (text, sort_value) in enumerate(cells):
                item = SortItem(text, sort_value=sort_value, row_id=view.id)
                if column in (4, 5):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if view.is_closed:
                    item.setBackground(_CLOSED_BACKGROUND)
                    item.setForeground(_CLOSED_FOREGROUND)
                self.table.setItem(row, column, item)
        self.data_table.apply()
        self.data_table.select_id(keep)
        self._update_buttons()

    def _selected_view(self) -> BookingView | None:
        selected = self.selected_id()
        return None if selected is None else self._views.get(selected)

    def _update_buttons(self) -> None:
        view = self._selected_view()
        self.edit_button.setEnabled(view is not None and view.can_edit)
        self.delete_button.setEnabled(view is not None and view.can_delete)
        self.reverse_button.setEnabled(view is not None and view.can_reverse)

    # Aktionen

    def _new(self) -> None:
        dialog = BookingDialog(self._bookings, self._master_data, self._actor_id, parent=self)
        if dialog.exec():
            self.refresh()

    def _new_transfer(self) -> None:
        dialog = BookingDialog(
            self._bookings,
            self._master_data,
            self._actor_id,
            preset_type=BookingType.BUDGET_TRANSFER,
            parent=self,
        )
        if dialog.exec():
            self.refresh()

    def _edit(self) -> None:
        view = self._selected_view()
        if view is None or not view.can_edit:
            return
        dialog = BookingDialog(
            self._bookings, self._master_data, self._actor_id, view.id, parent=self
        )
        if dialog.exec():
            self.refresh()

    def _delete(self) -> None:
        view = self._selected_view()
        if view is None:
            return
        answer = QMessageBox.question(
            self,
            "Buchung löschen",
            f"Die Buchung vom {format_date(view.booking_date)} über "
            f"{format_euro(view.amount_cents)} löschen?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run(lambda: self._bookings.delete(view.id, actor_id=self._actor_id))

    def _reverse(self) -> None:
        view = self._selected_view()
        if view is None:
            return
        answer = QMessageBox.question(
            self,
            "Buchung stornieren",
            "Die Buchung durch eine Minusbuchung auf derselben Seite stornieren?\n"
            "Das Buchungsdatum ist das Standarddatum im aktuellen Buchungsmonat.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            booking_date = self._bookings.default_booking_date()
            self._run(
                lambda: self._bookings.reverse(
                    view.id, booking_date=booking_date, actor_id=self._actor_id
                )
            )

    def _run(self, action: Callable[[], object]) -> None:
        try:
            action()
        except DomainError as error:
            self._warn(str(error))
            return
        self.refresh()

    def _warn(self, message: str) -> None:
        QMessageBox.warning(self, self.windowTitle(), message)
