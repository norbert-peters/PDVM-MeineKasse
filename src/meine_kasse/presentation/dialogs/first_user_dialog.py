from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.application.services.auth_service import AuthService
from meine_kasse.domain.errors import DomainError


class FirstUserDialog(QDialog):
    """Legt beim ersten Start den ersten Anwender mit erstmaligem Passwort an."""

    def __init__(self, auth: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auth = auth

        self.setWindowTitle("Meine Kasse – Ersten Anwender anlegen")
        self.name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()
        self.first_name_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.repeat_edit = QLineEdit()
        self.repeat_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Es ist noch kein Anwender vorhanden.\n"
                "Das erstmalige Passwort muss bei der ersten Anmeldung geändert werden."
            )
        )
        form = QFormLayout()
        form.addRow("Anmeldename:", self.name_edit)
        form.addRow("Nachname:", self.last_name_edit)
        form.addRow("Vorname:", self.first_name_edit)
        form.addRow("Anschrift:", self.address_edit)
        form.addRow("Erstmaliges Passwort:", self.password_edit)
        form.addRow("Passwort wiederholen:", self.repeat_edit)
        layout.addLayout(form)
        layout.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Anlegen")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Beenden")
        self.buttons.accepted.connect(self._try_create)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _try_create(self) -> None:
        if self.password_edit.text() != self.repeat_edit.text():
            self.error_label.setText("Die beiden Passwörter stimmen nicht überein.")
            return
        try:
            self._auth.create_user(
                name=self.name_edit.text(),
                last_name=self.last_name_edit.text(),
                first_name=self.first_name_edit.text(),
                address=self.address_edit.text(),
                initial_password=self.password_edit.text(),
            )
        except DomainError as error:
            self.error_label.setText(str(error))
            return
        self.accept()
