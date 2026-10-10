from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from meine_kasse.domain.repositories import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...
