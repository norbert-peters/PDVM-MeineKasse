"""Programmstart: Anmeldung, Pflicht-Passwortwechsel, Hauptmenü."""

import sys

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from meine_kasse.bootstrap import Container, build_container
from meine_kasse.config import database_path
from meine_kasse.presentation.dialogs.change_password_dialog import ChangePasswordDialog
from meine_kasse.presentation.dialogs.first_user_dialog import FirstUserDialog
from meine_kasse.presentation.dialogs.login_dialog import LoginDialog
from meine_kasse.presentation.main_window import MainWindow


def run(app: QApplication, container: Container) -> int:
    if (
        not container.auth.has_users()
        and FirstUserDialog(container.auth).exec() != QDialog.DialogCode.Accepted
    ):
        return 0

    while True:
        login_dialog = LoginDialog(container.auth)
        if login_dialog.exec() != QDialog.DialogCode.Accepted or login_dialog.login_result is None:
            return 0
        login = login_dialog.login_result

        if login.must_change_password:
            change_dialog = ChangePasswordDialog(container.auth, login.user_id, forced=True)
            if change_dialog.exec() != QDialog.DialogCode.Accepted:
                continue

        window = MainWindow(
            login,
            auth=container.auth,
            master_data=container.master_data,
            users=container.users,
            booking_control=container.booking_control,
            bookings=container.bookings,
            planning=container.planning,
            closing=container.closing,
            opening_balances=container.opening_balances,
        )
        window.show()
        app.exec()
        if not window.logout_requested:
            return 0


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Meine Kasse")
    try:
        container = build_container(database_path())
    except Exception as error:  # noqa: BLE001 - Startfehler dürfen die Oberfläche nicht abstürzen lassen
        QMessageBox.critical(
            None, "Meine Kasse", f"Die Datenbank konnte nicht geöffnet werden.\n\n{error}"
        )
        return 1
    try:
        return run(app, container)
    finally:
        container.database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
