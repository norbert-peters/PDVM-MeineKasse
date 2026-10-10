from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from meine_kasse.application.services.auth_service import AuthService
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.application.services.user_service import UserService
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
