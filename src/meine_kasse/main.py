"""Programmstart: Anmeldung, Pflicht-Passwortwechsel, Hauptmenü."""

import logging
import sys

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from meine_kasse import __version__
from meine_kasse.bootstrap import Container, build_container
from meine_kasse.build_info import build_label
from meine_kasse.config import database_path, log_dir
from meine_kasse.logging_setup import configure_logging, install_excepthook
from meine_kasse.presentation.dialogs.change_password_dialog import ChangePasswordDialog
from meine_kasse.presentation.dialogs.first_user_dialog import FirstUserDialog
from meine_kasse.presentation.dialogs.login_dialog import LoginDialog
from meine_kasse.presentation.main_window import MainWindow
from meine_kasse.selftest import SELFTEST_FLAG, run_selftest

logger = logging.getLogger("meine_kasse.main")


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
            backup=container.backup,
            user_settings=container.user_settings,
        )
        window.show()
        app.exec()
        if not window.logout_requested:
            return 0


def _report_crash(text: str) -> None:
    QMessageBox.critical(None, "Meine Kasse", text)


def main() -> int:
    log_path = configure_logging(log_dir())
    logger.info(
        "Start Meine Kasse %s (%s), Datenbank %s", __version__, build_label(), database_path()
    )
    if SELFTEST_FLAG in sys.argv[1:]:
        return run_selftest()
    app = QApplication(sys.argv)
    app.setApplicationName("Meine Kasse")
    install_excepthook(log_path, report=_report_crash)
    try:
        container = build_container(database_path())
    except Exception:  # noqa: BLE001 - Startfehler dürfen die Oberfläche nicht abstürzen lassen
        logger.exception("Die Datenbank konnte nicht geöffnet werden")
        QMessageBox.critical(
            None,
            "Meine Kasse",
            "Die Datenbank konnte nicht geöffnet werden.\n\n"
            f"Datenbank: {database_path()}\nDetails stehen in der Protokolldatei:\n{log_path}",
        )
        return 1
    try:
        return run(app, container)
    finally:
        container.database.dispose()
        logger.info("Ende Meine Kasse")


if __name__ == "__main__":
    raise SystemExit(main())
