"""Composition Root: verbindet Anwendungsdienste mit der Infrastruktur."""

from dataclasses import dataclass
from pathlib import Path

from meine_kasse.application.services.auth_service import AuthService
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.application.services.planning_service import PlanningService
from meine_kasse.application.services.user_service import UserService
from meine_kasse.infrastructure.database.migrate import upgrade_database
from meine_kasse.infrastructure.database.session import Database
from meine_kasse.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from meine_kasse.infrastructure.security.password_hasher import Argon2PasswordHasher


@dataclass(frozen=True, slots=True)
class Container:
    database: Database
    auth: AuthService
    master_data: MasterDataService
    users: UserService
    booking_control: BookingControlService
    bookings: BookingService
    planning: PlanningService
    closing: ClosingService


def build_container(database_file: Path) -> Container:
    """Öffnet die Datenbank, migriert sie auf den aktuellen Stand und erzeugt die Dienste."""
    database = Database.from_file(database_file)
    upgrade_database(database.engine)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(database.session_factory)

    return Container(
        database=database,
        auth=AuthService(uow_factory, Argon2PasswordHasher()),
        master_data=MasterDataService(uow_factory),
        users=UserService(uow_factory),
        booking_control=BookingControlService(uow_factory),
        bookings=BookingService(uow_factory),
        planning=PlanningService(uow_factory),
        closing=ClosingService(uow_factory),
    )
