from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QSpinBox, QWidget

from meine_kasse.application.services.booking_control_service import (
    MAX_YEAR,
    MIN_YEAR,
    BookingControlService,
)
from meine_kasse.presentation.dialogs.master_edit_dialog import MasterEditDialog
from meine_kasse.presentation.labels import MONTH_NAMES


class BookingControlDialog(MasterEditDialog):
    """Buchungssteuerung: aktueller Buchungsmonat und Planung."""

    def __init__(
        self, service: BookingControlService, actor_id: str, parent: QWidget | None = None
    ) -> None:
        super().__init__("Buchungssteuerung", parent)
        self._service = service
        self._actor_id = actor_id
        control = service.get()

        self.year_spin = QSpinBox()
        self.year_spin.setRange(MIN_YEAR, MAX_YEAR)
        self.year_spin.setValue(control.current_year)
        self.month_combo = QComboBox()
        for number, name in enumerate(MONTH_NAMES, start=1):
            self.month_combo.addItem(name, number)
        self.month_combo.setCurrentIndex(control.current_month - 1)
        self.planning_check = QCheckBox("Planung aktiviert (Ansatzsperre)")
        self.planning_check.setChecked(control.planning_enabled)

        self.form.addRow("Aktuelles Buchungsjahr:", self.year_spin)
        self.form.addRow("Aktueller Buchungsmonat:", self.month_combo)
        self.form.addRow("", self.planning_check)

        if control.last_closed_year is not None and control.last_closed_month is not None:
            closed = f"{control.last_closed_month:02d}/{control.last_closed_year}"
        else:
            closed = "noch keiner"
        info = QLabel(
            f"Letzter abgeschlossener Monat: {closed}\n"
            "Buchbar sind der aktuelle Buchungsmonat sowie ein Monat davor und danach."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #606060;")
        self.form.addRow("", info)

    def save(self) -> None:
        self._service.update(
            planning_enabled=self.planning_check.isChecked(),
            current_year=self.year_spin.value(),
            current_month=int(self.month_combo.currentData()),
            actor_id=self._actor_id,
        )
