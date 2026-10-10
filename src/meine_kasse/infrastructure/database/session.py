from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


class Database:
    """Kapselt Engine und Sessions. Einziger Ort, an dem die Datenbank geöffnet wird."""

    def __init__(self, url: str) -> None:
        self.engine = create_engine(url)
        _configure_sqlite(self.engine)
        self.session_factory: Callable[[], Session] = sessionmaker(
            self.engine, expire_on_commit=False
        )

    @classmethod
    def from_file(cls, path: Path) -> "Database":
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(f"sqlite:///{path.as_posix()}")

    def dispose(self) -> None:
        self.engine.dispose()


def _configure_sqlite(engine: Engine) -> None:
    """Fremdschlüssel aktivieren und jede Transaktion sofort mit Schreibsperre beginnen.

    `BEGIN IMMEDIATE` verhindert, dass Prüfungen (z. B. Ansatzsperre) und Schreibvorgang durch
    parallele Vorgänge auseinanderlaufen. Dafür muss der Treiber die Transaktion dem
    Programm überlassen (`isolation_level = None`).
    """

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
