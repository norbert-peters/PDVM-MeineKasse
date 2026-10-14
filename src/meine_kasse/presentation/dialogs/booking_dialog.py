from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QWidget,
)

from meine_kasse.application.services.booking_service import (
    BookingService,
    CostCenterInfo,
    PeriodState,
)
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import DomainError, PlanPeriodError, ValidationError
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.domain.value_objects.money import format_euro, parse_euro
from meine_kasse.presentation.dialogs.master_edit_dialog import MasterEditDialog
from meine_kasse.presentation.labels import BOOKING_TYPE_FIELDS, BOOKING_TYPE_LABELS

_KINDS = {
    BookingType.COST_CENTER_TO_ACCOUNT: (ObjectKind.COST_CENTER, ObjectKind.ACCOUNT),
    BookingType.ACCOUNT_TO_ACCOUNT: (ObjectKind.ACCOUNT, ObjectKind.ACCOUNT),
    BookingType.BUDGET_TRANSFER: (ObjectKind.COST_CENTER, ObjectKind.COST_CENTER),
}
_GOOD = "color: #1b6e2d;"
_BAD = "color: #b00020;"
_MUTED = "color: #606060;"


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _pydate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def _date_edit(value: date) -> QDateEdit:
    edit = QDateEdit(_qdate(value))
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd.MM.yyyy")
    return edit


class BookingDialog(MasterEditDialog):
    """Erfassen und Ändern einer Buchung.

    Der Betrag wird im Soll oder im Haben eingegeben (positiv oder negativ). Sobald ein Feld
    einen Betrag ungleich 0 enthält, ist das andere gesperrt.
    """

    def __init__(
        self,
        bookings: BookingService,
        master_data: MasterDataService,
        actor_id: str,
        booking_id: str | None = None,
        *,
        preset_type: BookingType | None = None,
        parent: QWidget | None = None,
    ) -> None:
        if booking_id is not None:
            title = "Buchung bearbeiten"
        elif preset_type is BookingType.BUDGET_TRANSFER:
            title = "Ansatzumbuchung"
        else:
            title = "Buchung erfassen"
        super().__init__(title, parent)
        self.setMinimumWidth(560)
        self._bookings = bookings
        self._master_data = master_data
        self._actor_id = actor_id
        self._booking_id = booking_id
        self._cost_centers: list[tuple[str, str]] = []
        self._accounts: list[tuple[str, str]] = []

        include_inactive = booking_id is not None
        for cost_center in master_data.list_cost_centers(include_inactive=include_inactive):
            suffix = "" if cost_center.is_active else " (inaktiv)"
            self._cost_centers.append(
                (f"{cost_center.number} – {cost_center.name}{suffix}", cost_center.id)
            )
        for account in master_data.list_accounts(include_inactive=include_inactive):
            suffix = "" if account.is_active else " (inaktiv)"
            self._accounts.append((f"{account.number} – {account.name}{suffix}", account.id))

        default_date = bookings.default_booking_date()
        self.type_combo = QComboBox()
        for booking_type, label in BOOKING_TYPE_LABELS.items():
            self.type_combo.addItem(label, booking_type.value)
        self.booking_date_edit = _date_edit(default_date)
        self.origin_date_edit = _date_edit(default_date)
        self.period_label = QLabel()
        self.leading_label = QLabel()
        self.leading_combo = QComboBox()
        self.leading_info = QLabel()
        self.second_label = QLabel()
        self.second_combo = QComboBox()
        self.second_info = QLabel()
        for info in (self.leading_info, self.second_info):
            info.setWordWrap(True)
            info.setStyleSheet(_MUTED)
        self.soll_edit = QLineEdit()
        self.haben_edit = QLineEdit()
        for edit in (self.soll_edit, self.haben_edit):
            edit.setPlaceholderText("0,00 €")
        self.merchant_edit = QLineEdit()
        self.text_edit = QPlainTextEdit()
        self.text_edit.setFixedHeight(60)
        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(_MUTED)

        self.form.addRow("Buchungsart:", self.type_combo)
        self.form.addRow("Buchungsdatum:", self.booking_date_edit)
        self.form.addRow("", self.period_label)
        self.form.addRow("Entstehungsdatum:", self.origin_date_edit)
        self.form.addRow(self.leading_label, self.leading_combo)
        self.form.addRow("", self.leading_info)
        self.form.addRow(self.second_label, self.second_combo)
        self.form.addRow("", self.second_info)
        self.form.addRow("Soll (€):", self.soll_edit)
        self.form.addRow("Haben (€):", self.haben_edit)
        self.form.addRow("", self.hint_label)
        self.form.addRow("Händler:", self.merchant_edit)
        self.form.addRow("Buchungstext:", self.text_edit)

        if booking_id is not None:
            self._load(booking_id)
        else:
            if preset_type is not None:
                self.type_combo.setCurrentIndex(self.type_combo.findData(preset_type.value))
                self.type_combo.setEnabled(False)
            self._fill_stellen()

        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.booking_date_edit.dateChanged.connect(lambda _date: self._refresh_info())
        self.origin_date_edit.dateChanged.connect(lambda _date: self._refresh_info())
        self.leading_combo.currentIndexChanged.connect(lambda _index: self._refresh_info())
        self.second_combo.currentIndexChanged.connect(lambda _index: self._refresh_info())
        self.soll_edit.textChanged.connect(self._sync_amount_lock)
        self.haben_edit.textChanged.connect(self._sync_amount_lock)
        self._sync_amount_lock()
        self._refresh_info()

    # Aufbau

    def booking_type(self) -> BookingType:
        return BookingType(self.type_combo.currentData())

    def _load(self, booking_id: str) -> None:
        booking = self._bookings.get_booking(booking_id)
        self.type_combo.setCurrentIndex(self.type_combo.findData(booking.booking_type.value))
        self.booking_date_edit.setDate(_qdate(booking.booking_date))
        self.origin_date_edit.setDate(_qdate(booking.origin_date))
        self._fill_stellen(
            leading=booking.legs[0].cost_center_id or booking.legs[0].account_id,
            second=booking.legs[1].cost_center_id or booking.legs[1].account_id,
        )
        amount_text = format_euro(booking.amount_cents)
        if booking.entry_side is Side.DEBIT:
            self.soll_edit.setText(amount_text)
        else:
            self.haben_edit.setText(amount_text)
        self.merchant_edit.setText(booking.merchant)
        self.text_edit.setPlainText(booking.booking_text)

    def _items_for(self, kind: ObjectKind) -> list[tuple[str, str]]:
        return self._cost_centers if kind is ObjectKind.COST_CENTER else self._accounts

    def _fill_stellen(self, leading: str | None = None, second: str | None = None) -> None:
        booking_type = self.booking_type()
        leading_text, second_text, hint = BOOKING_TYPE_FIELDS[booking_type]
        self.leading_label.setText(leading_text)
        self.second_label.setText(second_text)
        self.hint_label.setText(hint)
        leading_kind, second_kind = _KINDS[booking_type]
        for combo, kind, keep in (
            (self.leading_combo, leading_kind, leading),
            (self.second_combo, second_kind, second),
        ):
            combo.blockSignals(True)
            combo.clear()
            for label, entity_id in self._items_for(kind):
                combo.addItem(label, entity_id)
            if keep is not None:
                combo.setCurrentIndex(combo.findData(keep))
            combo.blockSignals(False)

    def _on_type_changed(self, _index: int) -> None:
        self._fill_stellen()
        self._refresh_info()

    # Anzeige

    def _refresh_info(self) -> None:
        booking_date = _pydate(self.booking_date_edit.date())
        try:
            status = self._bookings.period_status(booking_date)
        except DomainError as error:
            self.period_label.setText(str(error))
            return
        self.period_label.setText(status.message)
        self.period_label.setStyleSheet(_GOOD if status.state is PeriodState.OPEN else _BAD)

        leading_kind, second_kind = _KINDS[self.booking_type()]
        origin_date = _pydate(self.origin_date_edit.date())
        self._show_info(self.leading_info, leading_kind, self.leading_combo, origin_date)
        self._show_info(self.second_info, second_kind, self.second_combo, origin_date)

    def _show_info(
        self, label: QLabel, kind: ObjectKind, combo: QComboBox, plan_date: date
    ) -> None:
        entity_id = combo.currentData()
        if entity_id is None:
            label.setText("")
            return
        try:
            if kind is ObjectKind.COST_CENTER:
                label.setText(
                    _describe_cost_center(self._bookings.cost_center_info(entity_id, plan_date))
                )
            else:
                balance = self._bookings.account_balance(entity_id)
                label.setText(f"Kontostand (inkl. Anfangssaldo): {format_euro(balance)}")
        except DomainError as error:
            label.setText(str(error))

    def _sync_amount_lock(self) -> None:
        """Bei einem Betrag ungleich 0 ist das jeweils andere Feld gesperrt."""
        self.haben_edit.setEnabled(not _has_amount(self.soll_edit.text()))
        self.soll_edit.setEnabled(not _has_amount(self.haben_edit.text()))

    # Speichern

    def save(self) -> None:
        try:
            self._save_booking()
        except PlanPeriodError as error:
            QMessageBox.warning(self, "Buchung nicht möglich", str(error))
            raise
        self._show_reserve_notice()

    def _show_reserve_notice(self) -> None:
        """Hinweis nach dem Speichern, wenn die Rückstellung für die Zahlung nicht ausreicht."""
        cost_center_id = self.leading_combo.currentData()
        if self.booking_type() is not BookingType.COST_CENTER_TO_ACCOUNT or cost_center_id is None:
            return
        try:
            notice = self._bookings.reserve_notice(
                cost_center_id, _pydate(self.origin_date_edit.date())
            )
        except DomainError:
            return
        if notice:
            QMessageBox.information(self, "Hinweis zur Rückstellung", notice)

    def _save_booking(self) -> None:
        soll, haben = _amount(self.soll_edit.text()), _amount(self.haben_edit.text())
        if soll != 0 and haben != 0:
            raise ValidationError(
                "Ein Buchungssatz darf nur einen Betrag im Soll oder im Haben haben."
            )
        if soll == 0 and haben == 0:
            raise ValidationError("Bitte einen Betrag ungleich 0 im Soll oder im Haben eingeben.")
        entry_side, amount = (Side.DEBIT, soll) if soll != 0 else (Side.CREDIT, haben)

        booking_type = self.booking_type()
        leading_kind, second_kind = _KINDS[booking_type]
        leading_id, second_id = self.leading_combo.currentData(), self.second_combo.currentData()
        if leading_id is None or second_id is None:
            raise ValidationError("Bitte beide Stellen der Buchung wählen.")
        stellen = (Stelle(leading_kind, leading_id), Stelle(second_kind, second_id))
        booking_date = _pydate(self.booking_date_edit.date())
        origin_date = _pydate(self.origin_date_edit.date())
        if self._booking_id is None:
            self._bookings.post(
                booking_type=booking_type,
                entry_side=entry_side,
                amount_cents=amount,
                booking_date=booking_date,
                origin_date=origin_date,
                leading=stellen[0],
                second=stellen[1],
                merchant=self.merchant_edit.text(),
                booking_text=self.text_edit.toPlainText(),
                actor_id=self._actor_id,
            )
        else:
            self._bookings.update(
                self._booking_id,
                booking_type=booking_type,
                entry_side=entry_side,
                amount_cents=amount,
                booking_date=booking_date,
                origin_date=origin_date,
                leading=stellen[0],
                second=stellen[1],
                merchant=self.merchant_edit.text(),
                booking_text=self.text_edit.toPlainText(),
                actor_id=self._actor_id,
            )


def _has_amount(text: str) -> bool:
    """Ein Betrag ungleich 0 (oder eine unvollständige Eingabe) sperrt das andere Feld."""
    if not text.strip():
        return False
    try:
        return parse_euro(text) != 0
    except ValidationError:
        return True


def _amount(text: str) -> int:
    return parse_euro(text) if text.strip() else 0


def _describe_cost_center(info: CostCenterInfo) -> str:
    reserve = f"Rückstellungsbestand (bis Monat): {format_euro(info.reserve_cents)}"
    if not info.planning_active:
        return (
            f"Planung nicht aktiv · Bewegung {info.year}: {format_euro(info.movement_cents)} · "
            f"{reserve}"
        )
    return (
        f"Haushaltsrest: {format_euro(info.remaining_cents)} "
        f"(Ansatz {format_euro(info.annual_budget_cents)}, "
        f"Bewegung {format_euro(info.movement_cents)})\n"
        f"Monatsplan: {format_euro(info.month_plan_cents)} · "
        f"Ist im Monat: {format_euro(info.month_movement_cents)} · "
        f"{reserve}"
    )
