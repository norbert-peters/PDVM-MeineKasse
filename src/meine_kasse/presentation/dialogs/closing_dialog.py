from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
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
from meine_kasse.application.services.closing_service import ClosingOverview, ClosingService
from meine_kasse.domain.errors import DomainError
from meine_kasse.presentation.dialogs.reopen_closing_dialog import (
    ReopenClosingDialog,
    ReopeningHistoryDialog,
)
from meine_kasse.presentation.labels import MONTH_NAMES, format_date

_HEADERS = ["Monat", "Status", "Abgeschlossen am", "Signatur (SHA-256, Anfang)"]
_CLOSED_BACKGROUND = QBrush(QColor("#e6e6e6"))
_CLOSED_FOREGROUND = QBrush(QColor("#707070"))
_CURRENT_BACKGROUND = QBrush(QColor("#e3f2e1"))
_GOOD = "color: #1b6e2d;"
_BAD = "color: #b00020;"
_SIGNATURE_PREVIEW = 20


class ClosingDialog(QDialog):
    """Monats- und Jahresabschluss. Abgeschlossene Monate sind danach unveränderbar."""

    def __init__(
        self,
        closing: ClosingService,
        control: BookingControlService,
        actor_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Monats- und Jahresabschluss")
        self.resize(820, 560)
        self._closing = closing
        self._actor_id = actor_id
        self._overview: ClosingOverview | None = None

        self.year_spin = QSpinBox()
        self.year_spin.setRange(MIN_YEAR, MAX_YEAR)
        self.year_spin.setValue(control.get().current_year)
        self.year_spin.valueChanged.connect(lambda _value: self.refresh())

        self.current_label = QLabel()
        self.year_label = QLabel()
        self.reopen_label = QLabel()
        self.blocker_label = QLabel()
        self.blocker_label.setWordWrap(True)
        self.blocker_label.setStyleSheet("color: #606060;")
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        self.table = QTableWidget(12, len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.close_month_button = self._button("&Aktuellen Monat abschließen…", self._close_month)
        self.close_year_button = self._button("&Jahr abschließen…", self._close_year)
        self.reopen_button = self._button("Letzten Abschluss &wiedereröffnen…", self._reopen)
        self.history_button = self._button("Wiedereröffnungen &anzeigen…", self._show_history)
        self.verify_button = self._button("Abschlüsse &prüfen", self._verify)
        close_button = self._button("S&chließen", self.accept)

        top = QFormLayout()
        top.addRow("Jahr:", self.year_spin)
        top.addRow("Aktueller Buchungsmonat:", self.current_label)
        top.addRow("Jahresabschluss:", self.year_label)
        top.addRow("Nächster wiedereröffnbar:", self.reopen_label)

        buttons = QHBoxLayout()
        for button in (
            self.close_month_button,
            self.close_year_button,
            self.reopen_button,
            self.history_button,
            self.verify_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.blocker_label)
        layout.addWidget(self.message_label)
        layout.addLayout(buttons)
        self.refresh()

    @staticmethod
    def _button(text: str, handler: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False: handler())
        return button

    def refresh(self) -> None:
        try:
            overview = self._closing.get_overview(self.year_spin.value())
        except DomainError as error:
            self._show(str(error), bad=True)
            return
        self._overview = overview
        self.current_label.setText(f"{overview.current_month:02d}/{overview.current_year}")
        if overview.year_closed and overview.year_closed_on is not None:
            self.year_label.setText(
                f"abgeschlossen (fix) am {format_date(overview.year_closed_on)}"
            )
        else:
            self.year_label.setText("offen (frei)")

        for row, month in enumerate(overview.months):
            if month.is_closed:
                status = "abgeschlossen (fix)"
            elif month.is_current:
                status = "offen (frei) – aktueller Buchungsmonat"
            else:
                status = "offen (frei)"
            values = [
                MONTH_NAMES[month.month - 1],
                status,
                format_date(month.closed_on) if month.closed_on else "",
                month.signature[:_SIGNATURE_PREVIEW] + "…" if month.signature else "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if month.is_closed or overview.year_closed:
                    item.setBackground(_CLOSED_BACKGROUND)
                    item.setForeground(_CLOSED_FOREGROUND)
                elif month.is_current:
                    item.setBackground(_CURRENT_BACKGROUND)
                if column == 3:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)

        self.close_month_button.setEnabled(overview.can_close_month)
        self.close_year_button.setEnabled(overview.can_close_year)
        self.reopen_button.setEnabled(overview.can_reopen)
        self.reopen_label.setText(
            overview.reopen_target.label if overview.reopen_target else "kein Abschluss vorhanden"
        )
        blockers = [b for b in (overview.month_blocker, overview.year_blocker) if b]
        self.blocker_label.setText("\n".join(blockers))

    def _show(self, text: str, *, bad: bool = False, good: bool = False) -> None:
        self.message_label.setText(text)
        self.message_label.setStyleSheet(_BAD if bad else _GOOD if good else "")

    def _confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def _close_month(self) -> None:
        overview = self._overview
        if overview is None:
            return
        label = f"{overview.current_month:02d}/{overview.current_year}"
        if not self._confirm(
            "Monat abschließen",
            f"Den Monat {label} abschließen?\n\n"
            "Danach sind Buchungen und Planung dieses Monats nicht mehr änderbar. "
            "Korrekturen sind nur noch durch Storno in einem offenen Monat möglich.",
        ):
            return
        try:
            result = self._closing.close_month(actor_id=self._actor_id)
        except DomainError as error:
            self._show(str(error), bad=True)
            return
        self.year_spin.setValue(result.year)
        self.refresh()
        self._show(
            f"Der Monat {result.month:02d}/{result.year} wurde abgeschlossen. "
            f"Neuer Buchungsmonat: {result.next_month:02d}/{result.next_year}.",
            good=True,
        )

    def _close_year(self) -> None:
        year = self.year_spin.value()
        if not self._confirm(
            "Jahr abschließen",
            f"Das Jahr {year} abschließen?\n\n"
            "Danach ist das gesamte Jahr gesperrt und kann nicht mehr geändert werden.",
        ):
            return
        try:
            self._closing.close_year(year, actor_id=self._actor_id)
        except DomainError as error:
            self._show(str(error), bad=True)
            return
        self.refresh()
        self._show(f"Das Jahr {year} wurde abgeschlossen.", good=True)

    def _reopen(self) -> None:
        overview = self._overview
        if overview is None or overview.reopen_target is None:
            return
        target = overview.reopen_target
        dialog = ReopenClosingDialog(self._closing, target, self._actor_id, self)
        if not dialog.exec():
            return
        self.year_spin.setValue(target.year)
        self.refresh()
        self._show(
            f"{target.label} wurde wiedereröffnet und in der Historie dokumentiert.", good=True
        )

    def _show_history(self) -> None:
        ReopeningHistoryDialog(self._closing, self).exec()

    def _verify(self) -> None:
        try:
            checks = self._closing.verify_closures()
        except DomainError as error:
            self._show(str(error), bad=True)
            return
        if not checks:
            QMessageBox.information(self, "Abschlüsse prüfen", "Es gibt noch keine Abschlüsse.")
            return
        failed = [check for check in checks if not check.ok]
        lines = "\n".join(check.message for check in checks)
        if failed:
            self._show(
                f"{len(failed)} von {len(checks)} Abschlüssen weichen ab. "
                "Die Daten wurden nach dem Abschluss verändert.",
                bad=True,
            )
        else:
            self._show(f"Alle {len(checks)} Abschlüsse sind unverändert.", good=True)
        QMessageBox.information(self, "Abschlüsse prüfen", lines)
