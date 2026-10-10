"""Schnittstellen für den Datenzugriff. Die Implementierung liegt in der Infrastruktur."""

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol, Self

from meine_kasse.domain.entities import Account, AuditEntry, CostCenter, User


class UserRepository(Protocol):
    def add(self, user: User) -> None: ...

    def update(self, user: User) -> None: ...

    def get(self, user_id: str) -> User | None: ...

    def get_by_name(self, name: str) -> User | None:
        """Sucht einen Anwender ohne Beachtung der Groß-/Kleinschreibung."""
        ...

    def list_all(self) -> Sequence[User]: ...

    def count(self) -> int: ...


class CostCenterRepository(Protocol):
    def add(self, cost_center: CostCenter) -> None: ...

    def get(self, cost_center_id: str) -> CostCenter | None: ...

    def get_by_number(self, number: str) -> CostCenter | None: ...

    def list_all(self) -> Sequence[CostCenter]: ...


class AccountRepository(Protocol):
    def add(self, account: Account) -> None: ...

    def get(self, account_id: str) -> Account | None: ...

    def get_by_number(self, number: str) -> Account | None: ...

    def list_all(self) -> Sequence[Account]: ...


class AuditRepository(Protocol):
    def add(self, entry: AuditEntry) -> None: ...


class UnitOfWork(Protocol):
    """Eine Transaktion. Ohne `commit()` wird beim Verlassen zurückgerollt."""

    @property
    def users(self) -> UserRepository: ...

    @property
    def cost_centers(self) -> CostCenterRepository: ...

    @property
    def accounts(self) -> AccountRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...
