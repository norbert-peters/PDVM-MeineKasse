from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.domain.enums import ClosureKind
from meine_kasse.domain.services.closing_rules import MIN_REASON_LENGTH, ClosureRef
from meine_kasse.presentation.dialogs.master_edit_dialog import MasterEditDialog
from meine_kasse.presentation.labels import format_date


class ReopenClosingDialog(MasterEditDialog):
    """Öffnet den zuletzt liegenden Abschluss wieder. Eine Begründung ist Pflicht."""

    def __init__(
        self,
        closing: ClosingService,
        target: ClosureRef,
        actor_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Abschluss wiedereröffnen", parent)
        self._closing = closing
        self._target = target
        self._actor_id = actor_id

        warning = QLabel(
            f"<b>{target.label}</b> wird wiedereröffnet.<br><br>"
            "Der Zeitraum ist danach wieder änderbar, die bisherige Signatur wird verworfen. "
            "Das Wiedereröffnen wird mit Ihrem Namen, dem Datum, der Begründung und der "
            "verworfenen Signatur dauerhaft dokumentiert. Abschlüsse können nur in "
            "umgekehrter Reihenfolge wiedereröffnet werden."
        )
        warning.setWordWrap(True)
        warning.setTextFormat(Qt.TextFormat.RichText)
        self.content.insertWidget(0, warning)

        self.reason_edit = QPlainTextEdit()
        self.reason_edit.setPlaceholderText(f"Mindestens {MIN_REASON_LENGTH} Zeichen")
        self.reason_edit.setFixedHeight(90)
        self.form.addRow("Begründung:", self.reason_edit)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Wiedereröffnen")

    def save(self) -> None:
        reason = self.reason_edit.toPlainText()
        if self._target.kind is ClosureKind.YEAR:
            self._closing.reopen_year(self._target.year, reason=reason, actor_id=self._actor_id)
        else:
            assert self._target.month is not None
            self._closing.reopen_month(
                self._target.year, self._target.month, reason=reason, actor_id=self._actor_id
            )


class ReopeningHistoryDialog(QDialog):
    """Historie aller Wiedereröffnungen (jüngste zuerst)."""

    _HEADERS = [
        "Abschluss",
        "Wiedereröffnet am",
        "Von",
        "Begründung",
        "Ursprünglich abgeschlossen",
        "Signatur zuvor gültig",
    ]

    def __init__(self, closing: ClosingService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Wiedereröffnungen")
        self.resize(980, 420)

        self.table = QTableWidget(0, len(self._HEADERS))
        self.table.setHorizontalHeaderLabels(self._HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        info = QLabel(
            "„Signatur zuvor gültig: Nein“ bedeutet, dass die Daten des Zeitraums nach dem "
            "Abschluss verändert wurden."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #606060;")
        close_button = QPushButton("&Schließen")
        close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(info)
        layout.addLayout(buttons)

        entries = closing.list_reopenings()
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = [
                entry.ref.label,
                format_date(entry.reopened_on),
                entry.reopened_by,
                entry.reason,
                f"{format_date(entry.previous_closed_on)} ({entry.previous_closed_by})",
                "Ja" if entry.signature_was_valid else "Nein",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
