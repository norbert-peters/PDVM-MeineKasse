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


def _password_edit() -> QLineEdit:
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    return edit


class ChangePasswordDialog(QDialog):
    """Passwortwechsel. Beim erstmaligen Passwort ist der Wechsel Pflicht."""

    def __init__(
        self,
        auth: AuthService,
        user_id: str,
        *,
        forced: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._auth = auth
        self._user_id = user_id

        self.setWindowTitle("Passwort ändern")
        self.old_edit = _password_edit()
        self.new_edit = _password_edit()
        self.repeat_edit = _password_edit()
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        if forced:
            layout.addWidget(
                QLabel(
                    "Dies ist Ihre erste Anmeldung bzw. Ihr Passwort wurde zurückgesetzt.\n"
                    "Bitte vergeben Sie jetzt ein neues Passwort."
                )
            )
        form = QFormLayout()
        form.addRow("Bisheriges Passwort:", self.old_edit)
        form.addRow("Neues Passwort:", self.new_edit)
        form.addRow("Neues Passwort wiederholen:", self.repeat_edit)
        layout.addLayout(form)
        layout.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Passwort ändern")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        self.buttons.accepted.connect(self._try_change)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _try_change(self) -> None:
        if self.new_edit.text() != self.repeat_edit.text():
            self.error_label.setText("Die beiden neuen Passwörter stimmen nicht überein.")
            return
        try:
            self._auth.change_password(self._user_id, self.old_edit.text(), self.new_edit.text())
        except DomainError as error:
            self.error_label.setText(str(error))
            return
        self.accept()
