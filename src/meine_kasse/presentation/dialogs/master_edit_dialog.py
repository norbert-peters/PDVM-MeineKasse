from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.domain.errors import DomainError


class MasterEditDialog(QDialog):
    """Basis für Anlege- und Bearbeitungsdialoge. Fachliche Fehler erscheinen im Dialog."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        self.form = QFormLayout()
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.setWordWrap(True)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Speichern")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        self.buttons.accepted.connect(self._try_save)
        self.buttons.rejected.connect(self.reject)

        self.content = QVBoxLayout(self)
        self.content.addLayout(self.form)
        self.content.addWidget(self.error_label)
        self.content.addWidget(self.buttons)

    def save(self) -> None:
        """Speichert die Eingaben und löst bei fachlichen Fehlern einen `DomainError` aus."""
        raise NotImplementedError

    def _try_save(self) -> None:
        try:
            self.save()
        except DomainError as error:
            self.error_label.setText(str(error))
            return
        self.accept()
