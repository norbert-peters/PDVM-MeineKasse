from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QWidget,
)

from meine_kasse.application.services.booking_service import BookingService, PeriodState
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.domain.errors import DomainError, PlanPeriodError, ValidationError
from meine_kasse.domain.value_objects.money import format_euro, parse_euro
from meine_kasse.presentation.dialogs.booking_dialog import (
    _BAD,
    _GOOD,
    _MUTED,
    _date_edit,
    _describe_cost_center,
    _pydate,
    _qdate,
)
from meine_kasse.presentation.dialogs.master_edit_dialog import MasterEditDialog

_HINT = (
    "Die Umbuchung wird in zwei Buchungssätze geteilt: Das führende Konto wird mit seiner "
    "Kostenstelle im Soll belastet (Ausgabe), das Umbuchungskonto erhält den Betrag mit "
    "seiner Kostenstelle im Haben. Jede Kontobewegung hat so eine Kostenstelle als Gegenstelle."
)


class TransferDialog(MasterEditDialog):
    """Erfassen und Ändern einer Umbuchung zwischen zwei Konten mit je einer Kostenstelle."""

    def __init__(
        self,
        bookings: BookingService,
        master_data: MasterDataService,
        actor_id: str,
        transfer_id: str | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Umbuchung bearbeiten" if transfer_id else "Umbuchung", parent)
        self.setMinimumWidth(560)
        self._bookings = bookings
        self._actor_id = actor_id
        self._transfer_id = transfer_id

        include_inactive = transfer_id is not None
        cost_centers = [
            (f"{c.number} – {c.name}{'' if c.is_active else ' (inaktiv)'}", c.id)
            for c in master_data.list_cost_centers(include_inactive=include_inactive)
        ]
        accounts = [
            (f"{a.number} – {a.name}{'' if a.is_active else ' (inaktiv)'}", a.id)
            for a in master_data.list_accounts(include_inactive=include_inactive)
        ]

        default_date = bookings.default_booking_date()
        self.booking_date_edit: QDateEdit = _date_edit(default_date)
        self.origin_date_edit: QDateEdit = _date_edit(default_date)
        self.period_label = QLabel()
        self.leading_account_combo = self._combo(accounts)
        self.leading_account_info = self._info_label()
        self.leading_cost_center_combo = self._combo(cost_centers)
        self.leading_cost_center_info = self._info_label()
        self.transfer_account_combo = self._combo(accounts)
        self.transfer_account_info = self._info_label()
        self.transfer_cost_center_combo = self._combo(cost_centers)
        self.transfer_cost_center_info = self._info_label()
        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("0,00 €")
        self.merchant_edit = QLineEdit()
        self.text_edit = QPlainTextEdit()
        self.text_edit.setFixedHeight(60)
        hint = QLabel(_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(_MUTED)

        self.form.addRow("Buchungsdatum:", self.booking_date_edit)
        self.form.addRow("", self.period_label)
        self.form.addRow("Entstehungsdatum:", self.origin_date_edit)
        self.form.addRow("Führendes Konto (Soll):", self.leading_account_combo)
        self.form.addRow("", self.leading_account_info)
        self.form.addRow("Kostenstelle (Soll):", self.leading_cost_center_combo)
        self.form.addRow("", self.leading_cost_center_info)
        self.form.addRow("Umbuchungskonto (Haben):", self.transfer_account_combo)
        self.form.addRow("", self.transfer_account_info)
        self.form.addRow("Kostenstelle (Haben):", self.transfer_cost_center_combo)
        self.form.addRow("", self.transfer_cost_center_info)
        self.form.addRow("Betrag (€):", self.amount_edit)
        self.form.addRow("", hint)
        self.form.addRow("Händler:", self.merchant_edit)
        self.form.addRow("Buchungstext:", self.text_edit)

        if transfer_id is not None:
            self._load(transfer_id)

        self.booking_date_edit.dateChanged.connect(lambda _date: self._refresh_info())
        self.origin_date_edit.dateChanged.connect(lambda _date: self._refresh_info())
        for combo in (
            self.leading_account_combo,
            self.leading_cost_center_combo,
            self.transfer_account_combo,
            self.transfer_cost_center_combo,
        ):
            combo.currentIndexChanged.connect(lambda _index: self._refresh_info())
        self._refresh_info()

    @staticmethod
    def _combo(items: list[tuple[str, str]]) -> QComboBox:
        combo = QComboBox()
        for label, entity_id in items:
            combo.addItem(label, entity_id)
        return combo

    @staticmethod
    def _info_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setStyleSheet(_MUTED)
        return label

    def _load(self, transfer_id: str) -> None:
        debit, credit = self._bookings.get_transfer(transfer_id)
        self.booking_date_edit.setDate(_qdate(debit.booking_date))
        self.origin_date_edit.setDate(_qdate(debit.origin_date))
        for combo, entity_id in (
            (self.leading_cost_center_combo, debit.legs[0].cost_center_id),
            (self.leading_account_combo, debit.legs[1].account_id),
            (self.transfer_cost_center_combo, credit.legs[0].cost_center_id),
            (self.transfer_account_combo, credit.legs[1].account_id),
        ):
            combo.setCurrentIndex(combo.findData(entity_id))
        self.amount_edit.setText(format_euro(debit.amount_cents))
        self.merchant_edit.setText(debit.merchant)
        self.text_edit.setPlainText(debit.booking_text)

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

        origin_date = _pydate(self.origin_date_edit.date())
        for combo, label in (
            (self.leading_cost_center_combo, self.leading_cost_center_info),
            (self.transfer_cost_center_combo, self.transfer_cost_center_info),
        ):
            self._show_cost_center(combo, label, origin_date)
        for combo, label in (
            (self.leading_account_combo, self.leading_account_info),
            (self.transfer_account_combo, self.transfer_account_info),
        ):
            self._show_account(combo, label)

    def _show_cost_center(self, combo: QComboBox, label: QLabel, origin_date: date) -> None:
        entity_id = combo.currentData()
        if entity_id is None:
            label.setText("")
            return
        try:
            label.setText(
                _describe_cost_center(self._bookings.cost_center_info(entity_id, origin_date))
            )
        except DomainError as error:
            label.setText(str(error))

    def _show_account(self, combo: QComboBox, label: QLabel) -> None:
        entity_id = combo.currentData()
        if entity_id is None:
            label.setText("")
            return
        try:
            balance = self._bookings.account_balance(entity_id)
            label.setText(f"Kontostand (inkl. Anfangssaldo): {format_euro(balance)}")
        except DomainError as error:
            label.setText(str(error))

    # Speichern

    def save(self) -> None:
        try:
            self._save_transfer()
        except PlanPeriodError as error:
            QMessageBox.warning(self, "Buchung nicht möglich", str(error))
            raise
        self._show_reserve_notice()

    def _show_reserve_notice(self) -> None:
        """Hinweis nach dem Speichern, wenn die Rückstellung für die Ausgabe nicht ausreicht."""
        cost_center_id = self.leading_cost_center_combo.currentData()
        if cost_center_id is None:
            return
        try:
            notice = self._bookings.reserve_notice(
                cost_center_id, _pydate(self.origin_date_edit.date())
            )
        except DomainError:
            return
        if notice:
            QMessageBox.information(self, "Hinweis zur Rückstellung", notice)

    def _save_transfer(self) -> None:
        text = self.amount_edit.text()
        amount = parse_euro(text) if text.strip() else 0
        if amount == 0:
            raise ValidationError("Bitte einen Betrag ungleich 0 eingeben.")
        leading_cc, leading_account, transfer_cc, transfer_account = (
            self.leading_cost_center_combo.currentData(),
            self.leading_account_combo.currentData(),
            self.transfer_cost_center_combo.currentData(),
            self.transfer_account_combo.currentData(),
        )
        if None in (leading_cc, leading_account, transfer_cc, transfer_account):
            raise ValidationError("Bitte für beide Konten ein Konto und eine Kostenstelle wählen.")
        booking_date = _pydate(self.booking_date_edit.date())
        origin_date = _pydate(self.origin_date_edit.date())
        merchant, booking_text = self.merchant_edit.text(), self.text_edit.toPlainText()
        if self._transfer_id is None:
            self._bookings.post_transfer(
                amount_cents=amount,
                booking_date=booking_date,
                origin_date=origin_date,
                leading_cost_center_id=leading_cc,
                leading_account_id=leading_account,
                transfer_cost_center_id=transfer_cc,
                transfer_account_id=transfer_account,
                merchant=merchant,
                booking_text=booking_text,
                actor_id=self._actor_id,
            )
        else:
            self._bookings.update_transfer(
                self._transfer_id,
                amount_cents=amount,
                booking_date=booking_date,
                origin_date=origin_date,
                leading_cost_center_id=leading_cc,
                leading_account_id=leading_account,
                transfer_cost_center_id=transfer_cc,
                transfer_account_id=transfer_account,
                merchant=merchant,
                booking_text=booking_text,
                actor_id=self._actor_id,
            )
