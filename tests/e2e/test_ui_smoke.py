import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from meine_kasse.application.services.auth_service import AuthService, LoginResult  # noqa: E402
from meine_kasse.application.services.booking_control_service import (  # noqa: E402
    BookingControlService,
)
from meine_kasse.application.services.booking_service import BookingService  # noqa: E402
from meine_kasse.application.services.closing_service import ClosingService  # noqa: E402
from meine_kasse.application.services.master_data_service import MasterDataService  # noqa: E402
from meine_kasse.application.services.opening_balance_service import (  # noqa: E402
    OpeningBalanceService,
)
from meine_kasse.application.services.planning_service import PlanningService  # noqa: E402
from meine_kasse.application.services.user_service import UserService  # noqa: E402
from meine_kasse.presentation.dialogs.change_password_dialog import (  # noqa: E402
    ChangePasswordDialog,
)
from meine_kasse.presentation.dialogs.first_user_dialog import FirstUserDialog  # noqa: E402
from meine_kasse.presentation.dialogs.login_dialog import LoginDialog  # noqa: E402
from meine_kasse.presentation.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


def test_login_dialog_shows_neutral_message_on_failure(
    qapp: QApplication, auth: AuthService
) -> None:
    auth.create_user(name="anna", last_name="", first_name="", initial_password="Erstpasswort-1")
    dialog = LoginDialog(auth)
    dialog.name_edit.setText("anna")
    dialog.password_edit.setText("falsch-falsch")
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()

    assert dialog.error_label.text() == "Anmeldename oder Passwort ist falsch."
    assert dialog.login_result is None
    assert dialog.password_edit.text() == ""


def test_login_dialog_success_returns_result(qapp: QApplication, auth: AuthService) -> None:
    auth.create_user(name="anna", last_name="", first_name="", initial_password="Erstpasswort-1")
    dialog = LoginDialog(auth)
    dialog.name_edit.setText("anna")
    dialog.password_edit.setText("Erstpasswort-1")
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()

    assert dialog.login_result is not None
    assert dialog.login_result.must_change_password is True


def test_change_password_dialog_checks_repetition_and_changes(
    qapp: QApplication, auth: AuthService
) -> None:
    user_id = auth.create_user(
        name="anna", last_name="", first_name="", initial_password="Erstpasswort-1"
    )
    dialog = ChangePasswordDialog(auth, user_id, forced=True)
    dialog.old_edit.setText("Erstpasswort-1")
    dialog.new_edit.setText("Neues-Passwort-2")
    dialog.repeat_edit.setText("Anderes-Passwort-3")
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
    assert "stimmen nicht überein" in dialog.error_label.text()

    dialog.repeat_edit.setText("Neues-Passwort-2")
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
    assert auth.login("anna", "Neues-Passwort-2").must_change_password is False


def test_first_user_dialog_creates_user(qapp: QApplication, auth: AuthService) -> None:
    dialog = FirstUserDialog(auth)
    dialog.name_edit.setText("anna")
    dialog.password_edit.setText("Erstpasswort-1")
    dialog.repeat_edit.setText("Erstpasswort-1")
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
    assert auth.has_users()


def test_main_window_menu_enables_implemented_entries_and_keeps_planned_ones_disabled(
    qapp: QApplication,
    auth: AuthService,
    master_data: MasterDataService,
    users: UserService,
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    closing: ClosingService,
    openings: OpeningBalanceService,
) -> None:
    window = MainWindow(
        LoginResult("id", "Anna Muster", False),
        auth=auth,
        master_data=master_data,
        users=users,
        booking_control=booking_control,
        bookings=bookings,
        planning=planning,
        closing=closing,
        opening_balances=openings,
    )
    titles = [action.text() for action in window.menuBar().actions()]
    assert titles == ["&Datei", "&Stammdaten", "&Buchungen", "&Planung", "&Abschluss", "&Hilfe"]

    def entries(index: int) -> list[tuple[str, bool]]:
        menu = window.menuBar().actions()[index].menu()
        assert menu is not None
        return [(a.text(), a.isEnabled()) for a in menu.actions() if not a.isSeparator()]

    assert entries(1) == [
        ("Kostenstellen", True),
        ("Konten", True),
        ("Anwender", True),
        ("Kontenanfangssalden", True),
        ("Buchungssteuerung", True),
    ]
    assert entries(2) == [
        ("Buchungen", True),
        ("Buchung erfassen", True),
        ("Ansatzumbuchung", True),
    ]
    assert entries(3) == [("Kostenstellenplanung", True)]
    assert entries(4) == [("Monats- und Jahresabschluss", True)]
    assert "Anna Muster" in window.statusBar().currentMessage()
