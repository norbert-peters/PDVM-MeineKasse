from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox

from meine_kasse import __version__
from meine_kasse.application.services.auth_service import AuthService, LoginResult
from meine_kasse.application.services.backup_service import BackupService
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.application.services.document_service import DocumentService
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.application.services.opening_balance_service import OpeningBalanceService
from meine_kasse.application.services.planning_service import PlanningService
from meine_kasse.application.services.report_service import ReportService
from meine_kasse.application.services.user_service import UserService
from meine_kasse.application.services.user_settings_service import UserSettingsService
from meine_kasse.build_info import build_label
from meine_kasse.config import database_path, documents_dir, log_dir
from meine_kasse.domain.enums import BookingType
from meine_kasse.domain.errors import DomainError
from meine_kasse.presentation.dialogs.account_dialogs import AccountListDialog
from meine_kasse.presentation.dialogs.booking_control_dialog import BookingControlDialog
from meine_kasse.presentation.dialogs.booking_dialog import BookingDialog
from meine_kasse.presentation.dialogs.booking_list_dialog import BookingListDialog
from meine_kasse.presentation.dialogs.closing_dialog import ClosingDialog
from meine_kasse.presentation.dialogs.cost_center_dialogs import CostCenterListDialog
from meine_kasse.presentation.dialogs.document_archive_dialog import DocumentArchiveDialog
from meine_kasse.presentation.dialogs.income_planning_dialog import IncomePlanningDialog
from meine_kasse.presentation.dialogs.liquidity_dialog import LiquidityDialog
from meine_kasse.presentation.dialogs.opening_balances_dialog import OpeningBalancesDialog
from meine_kasse.presentation.dialogs.planning_dialog import PlanningDialog
from meine_kasse.presentation.dialogs.report_dialog import ReportDialog
from meine_kasse.presentation.dialogs.user_dialogs import UserListDialog
from meine_kasse.presentation.widgets.data_table import TablePreferences
from meine_kasse.presentation.widgets.pdf_export import PdfExporter

_PLANNED_TIP = "In Vorbereitung"


class MainWindow(QMainWindow):
    """Hauptmenü nach der Anmeldung. Weitere fachliche Dialoge folgen schrittweise."""

    def __init__(
        self,
        login: LoginResult,
        *,
        auth: AuthService,
        master_data: MasterDataService,
        users: UserService,
        booking_control: BookingControlService,
        bookings: BookingService,
        planning: PlanningService,
        closing: ClosingService,
        opening_balances: OpeningBalanceService,
        backup: BackupService,
        user_settings: UserSettingsService | None = None,
        documents: DocumentService | None = None,
        reports: ReportService | None = None,
    ) -> None:
        super().__init__()
        self.logout_requested = False
        self._login = login
        self._exporter = None if documents is None else PdfExporter(documents, login.user_id)
        self._reports = reports
        self._preferences = (
            None
            if user_settings is None
            else TablePreferences(user_settings, login.user_id, self._exporter)
        )
        self._auth = auth
        self._master_data = master_data
        self._users = users
        self._booking_control = booking_control
        self._bookings = bookings
        self._planning = planning
        self._closing = closing
        self._opening_balances = opening_balances
        self._backup = backup

        self.setWindowTitle("Meine Kasse")
        self.resize(900, 600)
        welcome = QLabel(f"Willkommen, {login.display_name}.")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(welcome)
        self.statusBar().showMessage(f"Angemeldet: {login.display_name}")

        self._build_menus()

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&Datei")
        backup_action = QAction("&Datensicherung erstellen…", self)
        backup_action.triggered.connect(self._create_backup)
        logout = QAction("&Abmelden", self)
        logout.triggered.connect(self._logout)
        quit_action = QAction("&Beenden", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(backup_action)
        file_menu.addSeparator()
        file_menu.addAction(logout)
        file_menu.addAction(quit_action)

        master_menu = bar.addMenu("&Stammdaten")
        self._action(master_menu, "Kostenstellen", self._open_cost_centers)
        self._action(master_menu, "Konten", self._open_accounts)
        self._action(master_menu, "Anwender", self._open_users)
        self._action(master_menu, "Kontenanfangssalden", self._open_opening_balances)
        master_menu.addSeparator()
        self._action(master_menu, "Buchungssteuerung", self._open_booking_control)

        booking_menu = bar.addMenu("&Buchungen")
        self._action(booking_menu, "Buchungen", self._open_bookings)
        self._action(booking_menu, "Buchung erfassen", self._new_booking)
        self._action(booking_menu, "Ansatzumbuchung", self._new_budget_transfer)

        planning_menu = bar.addMenu("&Planung")
        self._action(planning_menu, "Kostenstellenplanung", self._open_planning)
        self._action(planning_menu, "Einnahmenplanung", self._open_income_planning)
        self._action(planning_menu, "Liquiditätsplanung", self._open_liquidity)
        closing_menu = bar.addMenu("&Abschluss")
        self._action(closing_menu, "Monats- und Jahresabschluss", self._open_closing)

        if self._reports is not None and self._exporter is not None:
            report_menu = bar.addMenu("A&uswertung")
            self._action(report_menu, "Auswertung…", self._open_report)
            self._action(report_menu, "Dokumentenarchiv…", self._open_documents)

        help_menu = bar.addMenu("&Hilfe")
        self._action(help_menu, "&Über Meine Kasse", self._about)

    def _action(self, menu: QMenu, title: str, handler: Callable[[], None]) -> QAction:
        action = QAction(title, self)
        action.triggered.connect(lambda _checked=False: handler())
        menu.addAction(action)
        return action

    def _planned_menu(self, menu: QMenu, titles: list[str]) -> None:
        for title in titles:
            action = QAction(title, self)
            action.setEnabled(False)
            action.setStatusTip(_PLANNED_TIP)
            menu.addAction(action)

    def _open_cost_centers(self) -> None:
        CostCenterListDialog(
            self._master_data, self._login.user_id, self, preferences=self._preferences
        ).exec()

    def _open_accounts(self) -> None:
        AccountListDialog(
            self._master_data, self._login.user_id, self, preferences=self._preferences
        ).exec()

    def _open_users(self) -> None:
        UserListDialog(
            self._auth, self._users, self._login.user_id, self, preferences=self._preferences
        ).exec()

    def _open_planning(self) -> None:
        PlanningDialog(self._planning, self._booking_control, self._login.user_id, self).exec()

    def _open_liquidity(self) -> None:
        LiquidityDialog(self._planning, self._booking_control, self).exec()

    def _open_income_planning(self) -> None:
        IncomePlanningDialog(
            self._planning, self._booking_control, self._login.user_id, self
        ).exec()

    def _open_report(self) -> None:
        if self._reports is not None and self._exporter is not None:
            ReportDialog(self._reports, self._exporter, self._login.user_id, self).exec()

    def _open_documents(self) -> None:
        if self._exporter is not None:
            DocumentArchiveDialog(self._exporter, self, preferences=self._preferences).exec()

    def _open_closing(self) -> None:
        ClosingDialog(self._closing, self._booking_control, self._login.user_id, self).exec()

    def _open_opening_balances(self) -> None:
        OpeningBalancesDialog(
            self._opening_balances, self._booking_control, self._login.user_id, self
        ).exec()

    def _open_booking_control(self) -> None:
        BookingControlDialog(self._booking_control, self._login.user_id, self).exec()

    def _open_bookings(self) -> None:
        BookingListDialog(
            self._bookings,
            self._master_data,
            self._booking_control,
            self._login.user_id,
            self,
            preferences=self._preferences,
        ).exec()

    def _new_booking(self) -> None:
        BookingDialog(self._bookings, self._master_data, self._login.user_id, parent=self).exec()

    def _new_budget_transfer(self) -> None:
        BookingDialog(
            self._bookings,
            self._master_data,
            self._login.user_id,
            preset_type=BookingType.BUDGET_TRANSFER,
            parent=self,
        ).exec()

    def _create_backup(self) -> None:
        suggestion = str(Path.home() / self._backup.suggested_file_name())
        chosen, _filter = QFileDialog.getSaveFileName(
            self, "Datensicherung erstellen", suggestion, "SQLite-Datei (*.sqlite)"
        )
        if not chosen:
            return
        try:
            target = self._backup.create_backup(Path(chosen))
        except DomainError as error:
            QMessageBox.warning(self, "Datensicherung", str(error))
            return
        QMessageBox.information(
            self,
            "Datensicherung",
            f"Die Sicherung wurde erstellt:\n{target}\n\n"
            f"Die Dokumente liegen im Ordner:\n{self._backup.documents_target(target)}",
        )

    def _logout(self) -> None:
        self.logout_requested = True
        self.close()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "Über Meine Kasse",
            f"Meine Kasse {__version__}\n"
            f"{build_label()}\n"
            "Einfache Haushaltsbuchhaltung auf Kostenstellen und Konten.\n\n"
            f"Datenbank: {database_path()}\n"
            f"Dokumente: {documents_dir()}\n"
            f"Protokolle: {log_dir()}",
        )
