from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol

from meine_kasse.domain.repositories import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]
Clock = Callable[[], datetime]
Today = Callable[[], date]


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_today() -> date:
    return date.today()


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...
