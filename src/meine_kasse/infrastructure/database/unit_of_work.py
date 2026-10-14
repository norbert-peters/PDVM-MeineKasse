from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from meine_kasse.infrastructure.database.repositories import (
    SqlAccountRepository,
    SqlAuditRepository,
    SqlBookingControlRepository,
    SqlBookingRepository,
    SqlClosureRepository,
    SqlCostCenterRepository,
    SqlOpeningBalanceRepository,
    SqlPlanRepository,
    SqlUserRepository,
    SqlUserSettingRepository,
)


class SqlAlchemyUnitOfWork:
    """Eine Transaktion. Ohne `commit()` wird beim Verlassen zurückgerollt."""

    users: SqlUserRepository
    user_settings: SqlUserSettingRepository
    cost_centers: SqlCostCenterRepository
    accounts: SqlAccountRepository
    audit: SqlAuditRepository
    booking_control: SqlBookingControlRepository
    closures: SqlClosureRepository
    bookings: SqlBookingRepository
    opening_balances: SqlOpeningBalanceRepository
    plans: SqlPlanRepository

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Self:
        session = self._session_factory()
        self._session = session
        self.users = SqlUserRepository(session)
        self.user_settings = SqlUserSettingRepository(session)
        self.cost_centers = SqlCostCenterRepository(session)
        self.accounts = SqlAccountRepository(session)
        self.audit = SqlAuditRepository(session)
        self.booking_control = SqlBookingControlRepository(session)
        self.closures = SqlClosureRepository(session)
        self.bookings = SqlBookingRepository(session)
        self.opening_balances = SqlOpeningBalanceRepository(session)
        self.plans = SqlPlanRepository(session)
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
