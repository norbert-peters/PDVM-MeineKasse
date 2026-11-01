from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from meine_kasse.application.reporting.pdf_model import PdfTable
from meine_kasse.domain.repositories import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]
Clock = Callable[[], datetime]
Today = Callable[[], date]


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_today() -> date:
    return date.today()


class PdfRenderer(Protocol):
    """Schreibt eine Tabelle als PDF-Datei. Die Umsetzung liegt in der Infrastruktur."""

    def render(self, table: PdfTable, target: Path) -> None: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...


class DatabaseBackup(Protocol):
    """Erzeugt eine konsistente Kopie der Datenbank."""

    def backup_to(self, target: Path) -> None: ...
