from collections.abc import Sequence

from PySide6.QtWidgets import QDialogButtonBox, QLabel, QLineEdit, QMessageBox, QWidget

from meine_kasse.application.services.auth_service import AuthService
from meine_kasse.application.services.user_service import UserService
from meine_kasse.domain.errors import ValidationError
from meine_kasse.presentation.dialogs.master_edit_dialog import MasterEditDialog
from meine_kasse.presentation.dialogs.master_list_dialog import ListRow, MasterListDialog


def _password_edit() -> QLineEdit:
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    return edit


class UserEditDialog(MasterEditDialog):
    """Legt einen Anwender an (mit erstmaligem Passwort) oder ändert seine Stammdaten."""

    def __init__(
        self,
        auth: AuthService,
        users: UserService,
        actor_id: str,
        user_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Anwender bearbeiten" if user_id else "Neuer Anwender", parent)
        self._auth = auth
        self._users = users
        self._actor_id = actor_id
        self._user_id = user_id

        self.name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()
        self.first_name_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.password_edit = _password_edit()
        self.repeat_edit = _password_edit()

        self.form.addRow("Anmeldename:", self.name_edit)
        self.form.addRow("Nachname:", self.last_name_edit)
        self.form.addRow("Vorname:", self.first_name_edit)
        self.form.addRow("Anschrift:", self.address_edit)

        if user_id is None:
            self.form.addRow("Erstmaliges Passwort:", self.password_edit)
            self.form.addRow("Passwort wiederholen:", self.repeat_edit)
            hint = QLabel("Das erstmalige Passwort muss bei der ersten Anmeldung geändert werden.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #606060;")
            self.form.addRow("", hint)
        else:
            current = users.get_user(user_id)
            self.name_edit.setText(current.name)
            self.last_name_edit.setText(current.last_name)
            self.first_name_edit.setText(current.first_name)
            self.address_edit.setText(current.address)

    def save(self) -> None:
        if self._user_id is None:
            if self.password_edit.text() != self.repeat_edit.text():
                raise ValidationError("Die beiden Passwörter stimmen nicht überein.")
            self._auth.create_user(
                name=self.name_edit.text(),
                last_name=self.last_name_edit.text(),
                first_name=self.first_name_edit.text(),
                address=self.address_edit.text(),
                initial_password=self.password_edit.text(),
                actor_id=self._actor_id,
            )
        else:
            self._users.update_user(
                self._user_id,
                name=self.name_edit.text(),
                last_name=self.last_name_edit.text(),
                first_name=self.first_name_edit.text(),
                address=self.address_edit.text(),
                actor_id=self._actor_id,
            )


class InitialPasswordDialog(MasterEditDialog):
    """Legt ein neues erstmaliges Passwort fest. Der Anwender muss es bei der Anmeldung ändern."""

    def __init__(
        self,
        auth: AuthService,
        actor_id: str,
        user_id: str,
        user_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Erstmaliges Passwort festlegen", parent)
        self._auth = auth
        self._actor_id = actor_id
        self._user_id = user_id

        self.password_edit = _password_edit()
        self.repeat_edit = _password_edit()
        info = QLabel(
            f"Neues erstmaliges Passwort für '{user_name}'.\n"
            "Das aktuelle Passwort wird damit ersetzt, der Anwender muss es bei der "
            "nächsten Anmeldung ändern."
        )
        info.setWordWrap(True)
        self.content.insertWidget(0, info)
        self.form.addRow("Erstmaliges Passwort:", self.password_edit)
        self.form.addRow("Passwort wiederholen:", self.repeat_edit)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Festlegen")

    def save(self) -> None:
        if self.password_edit.text() != self.repeat_edit.text():
            raise ValidationError("Die beiden Passwörter stimmen nicht überein.")
        self._auth.set_initial_password(self._user_id, self.password_edit.text(), self._actor_id)


class UserListDialog(MasterListDialog):
    def __init__(
        self,
        auth: AuthService,
        users: UserService,
        actor_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Anwender", ["Anmeldename", "Nachname", "Vorname", "Passwort"], parent)
        self._auth = auth
        self._users = users
        self._actor_id = actor_id
        self.initial_password_button = self.add_action(
            "&Erstpasswort festlegen…", self._set_initial_password
        )
        self.reset_button = self.add_action("Auf Erstpasswort &zurücksetzen", self._reset_password)
        self.refresh()

    def load_rows(self, include_inactive: bool) -> Sequence[ListRow]:
        return [
            ListRow(
                id=user.id,
                cells=[
                    user.name,
                    user.last_name,
                    user.first_name,
                    "Wechsel erforderlich" if user.must_change_password else "",
                ],
                active=user.is_active,
            )
            for user in self._users.list_users(include_inactive=include_inactive)
        ]

    def open_editor(self, entity_id: str | None) -> bool:
        dialog = UserEditDialog(self._auth, self._users, self._actor_id, entity_id, self)
        return bool(dialog.exec())

    def apply_active(self, entity_id: str, active: bool) -> None:
        self._users.set_active(entity_id, active, actor_id=self._actor_id)

    def _set_initial_password(self, user_id: str) -> None:
        user = self._users.get_user(user_id)
        InitialPasswordDialog(self._auth, self._actor_id, user_id, user.name, self).exec()

    def _reset_password(self, user_id: str) -> None:
        user = self._users.get_user(user_id)
        answer = QMessageBox.question(
            self,
            "Passwort zurücksetzen",
            f"Das Passwort von '{user.name}' auf das erstmalige Passwort zurücksetzen?\n"
            "Der Anwender muss es bei der nächsten Anmeldung ändern.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._auth.reset_to_initial_password(user_id, self._actor_id)
