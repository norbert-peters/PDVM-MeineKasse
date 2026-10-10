from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from meine_kasse.infrastructure.database.repositories import (
    SqlAccountRepository,
    SqlAuditRepository,
    SqlCostCenterRepository,
    SqlUserRepository,
)


class SqlAlchemyUnitOfWork:
    """Eine Transaktion. Ohne `commit()` wird beim Verlassen zurückgerollt."""

    users: SqlUserRepository
    cost_centers: SqlCostCenterRepository
    accounts: SqlAccountRepository
    audit: SqlAuditRepository

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Self:
        session = self._session_factory()
        self._session = session
        self.users = SqlUserRepository(session)
        self.cost_centers = SqlCostCenterRepository(session)
        self.accounts = SqlAccountRepository(session)
        self.audit = SqlAuditRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            session.rollback()
        finally:
            session.close()
            self._session = None

    def commit(self) -> None:
        self._require_session().commit()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Die Unit of Work wurde nicht mit 'with' geöffnet.")
        return self._session
