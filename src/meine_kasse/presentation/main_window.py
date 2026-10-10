from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QMainWindow, QMenu, QMessageBox

from meine_kasse import __version__
from meine_kasse.application.services.auth_service import LoginResult

_PLANNED_TIP = "In Vorbereitung"


class MainWindow(QMainWindow):
    """Hauptmenü nach der Anmeldung. Fachliche Dialoge folgen schrittweise."""

    def __init__(self, login: LoginResult) -> None:
        super().__init__()
        self.logout_requested = False

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
        logout = QAction("&Abmelden", self)
        logout.triggered.connect(self._logout)
        quit_action = QAction("&Beenden", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(logout)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        self._planned_menu(bar.addMenu("&Stammdaten"), ["Kostenstellen", "Konten", "Anwender"])
        self._planned_menu(bar.addMenu("&Buchungen"), ["Buchung erfassen", "Ansatzumbuchung"])
        self._planned_menu(bar.addMenu("&Planung"), ["Kostenstellenplanung"])
        self._planned_menu(bar.addMenu("&Abschluss"), ["Monatsabschluss", "Jahresabschluss"])

        help_menu = bar.addMenu("&Hilfe")
        about = QAction("&Über Meine Kasse", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _planned_menu(self, menu: QMenu, titles: list[str]) -> None:
        for title in titles:
            action = QAction(title, self)
            action.setEnabled(False)
            action.setStatusTip(_PLANNED_TIP)
            menu.addAction(action)

    def _logout(self) -> None:
        self.logout_requested = True
        self.close()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "Über Meine Kasse",
            f"Meine Kasse {__version__}\n"
            "Einfache Haushaltsbuchhaltung auf Kostenstellen und Konten.",
        )
