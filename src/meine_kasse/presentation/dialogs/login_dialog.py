from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.application.services.auth_service import AuthService, LoginResult
from meine_kasse.domain.errors import DomainError


class LoginDialog(QDialog):
    """Anmeldung mit Anwendername und Passwort."""

    def __init__(self, auth: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auth = auth
        self.login_result: LoginResult | None = None

        self.setWindowTitle("Meine Kasse – Anmeldung")
        self.name_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Anmeldename:", self.name_edit)
        form.addRow("Passwort:", self.password_edit)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Anmelden")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Beenden")
        self.buttons.accepted.connect(self._try_login)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)

    def _try_login(self) -> None:
        try:
            self.login_result = self._auth.login(self.name_edit.text(), self.password_edit.text())
        except DomainError as error:
            self.error_label.setText(str(error))
            self.password_edit.clear()
            self.password_edit.setFocus()
            return
        self.accept()
