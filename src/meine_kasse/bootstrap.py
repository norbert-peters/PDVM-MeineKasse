"""Composition Root: verbindet Anwendungsdienste mit der Infrastruktur."""

from dataclasses import dataclass
from pathlib import Path

from meine_kasse.application.services.auth_service import AuthService
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
from meine_kasse.config import DOCUMENTS_FOLDER
from meine_kasse.infrastructure.database.migrate import upgrade_database
from meine_kasse.infrastructure.database.session import Database
from meine_kasse.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from meine_kasse.infrastructure.reporting.pdf_renderer import ReportlabPdfRenderer
from meine_kasse.infrastructure.security.password_hasher import Argon2PasswordHasher


@dataclass(frozen=True, slots=True)
class Container:
    database: Database
    auth: AuthService
    master_data: MasterDataService
    users: UserService
    user_settings: UserSettingsService
    booking_control: BookingControlService
    bookings: BookingService
    planning: PlanningService
    closing: ClosingService
    opening_balances: OpeningBalanceService
    backup: BackupService
    documents: DocumentService
    reports: ReportService


def build_container(database_file: Path, documents_directory: Path | None = None) -> Container:
    """Öffnet die Datenbank, migriert sie auf den aktuellen Stand und erzeugt die Dienste.

    Das Dokumentenverzeichnis liegt standardmäßig neben der Datenbank."""
    database = Database.from_file(database_file)
    upgrade_database(database.engine)
    documents_dir = documents_directory or database_file.parent / DOCUMENTS_FOLDER

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(database.session_factory)

    planning = PlanningService(uow_factory)
    planning.refresh_reserves()
    documents = DocumentService(uow_factory, ReportlabPdfRenderer(), documents_dir)

    return Container(
        database=database,
        auth=AuthService(uow_factory, Argon2PasswordHasher()),
        master_data=MasterDataService(uow_factory),
        users=UserService(uow_factory),
        user_settings=UserSettingsService(uow_factory),
        booking_control=BookingControlService(uow_factory),
        bookings=BookingService(uow_factory),
        planning=planning,
        closing=ClosingService(uow_factory),
        opening_balances=OpeningBalanceService(uow_factory),
        backup=BackupService(database, database_file, documents_dir=documents_dir),
        documents=documents,
        reports=ReportService(uow_factory, planning, documents),
    )
