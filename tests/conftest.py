from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from meine_kasse.application.services.auth_service import AuthService
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.application.services.planning_service import PlanningService
from meine_kasse.application.services.user_service import UserService
from meine_kasse.domain.enums import AccountType, CostCenterKind
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.infrastructure.database.migrate import upgrade_database
from meine_kasse.infrastructure.database.session import Database
from meine_kasse.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from meine_kasse.infrastructure.security.password_hasher import Argon2PasswordHasher


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database.from_file(tmp_path / "test.sqlite")
    upgrade_database(db.engine)
    yield db
    db.dispose()


@pytest.fixture
def uow_factory(database: Database) -> Callable[[], UnitOfWork]:
    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(database.session_factory)

    return factory


@pytest.fixture
def auth(uow_factory: Callable[[], UnitOfWork]) -> AuthService:
    return AuthService(uow_factory, Argon2PasswordHasher())


@pytest.fixture
def master_data(uow_factory: Callable[[], UnitOfWork]) -> MasterDataService:
    return MasterDataService(uow_factory)


@pytest.fixture
def users(uow_factory: Callable[[], UnitOfWork]) -> UserService:
    return UserService(uow_factory)


TODAY = date(2026, 5, 15)
INITIAL = "Erstpasswort-1"


@dataclass(frozen=True)
class World:
    """Gemeinsame Stammdaten für Buchungs- und Planungstests."""

    actor: str
    cc_a: str
    cc_b: str
    cc_free: str  # Kostenstelle ohne Plan
    giro: str
    savings: str


@pytest.fixture
def world(auth: AuthService, master_data: MasterDataService) -> World:
    actor = auth.create_user(name="admin", last_name="A", first_name="A", initial_password=INITIAL)
    start = date(2026, 1, 1)
    return World(
        actor=actor,
        cc_a=master_data.create_cost_center(number="100", name="Lebensmittel", valid_from=start),
        cc_b=master_data.create_cost_center(number="200", name="Reisen", valid_from=start),
        cc_free=master_data.create_cost_center(
            number="300", name="Sonstiges", valid_from=start, kind=CostCenterKind.WITHOUT_PLAN
        ),
        giro=master_data.create_account(
            number="1000", name="Girokonto", account_type=AccountType.CHECKING
        ),
        savings=master_data.create_account(
            number="2000", name="Sparkonto", account_type=AccountType.SAVINGS
        ),
    )


@pytest.fixture
def planning(uow_factory: Callable[[], UnitOfWork]) -> PlanningService:
    return PlanningService(uow_factory, today=lambda: TODAY)


@pytest.fixture
def closing(uow_factory: Callable[[], UnitOfWork]) -> ClosingService:
    return ClosingService(uow_factory, today=lambda: TODAY)


@pytest.fixture
def booking_control(uow_factory: Callable[[], UnitOfWork]) -> BookingControlService:
    return BookingControlService(uow_factory, today=lambda: TODAY)


@pytest.fixture
def bookings(uow_factory: Callable[[], UnitOfWork]) -> BookingService:
    return BookingService(uow_factory, today=lambda: TODAY)
