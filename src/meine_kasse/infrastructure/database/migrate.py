from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def upgrade_database(engine: Engine, revision: str = "head") -> None:
    """Bringt die Datenbank auf den gewünschten Schemastand."""
    _migrate(engine, command.upgrade, revision)


def downgrade_database(engine: Engine, revision: str) -> None:
    """Setzt die Datenbank auf einen früheren Schemastand zurück (z. B. für Tests)."""
    _migrate(engine, command.downgrade, revision)


def _migrate(engine: Engine, action: Callable[[Config, str], None], revision: str) -> None:
    """Führt die Migration in einer Transaktion aus.

    SQLite baut Tabellen für Änderungen an Einschränkungen neu auf (`batch_alter_table`). Das
    Löschen der alten Tabelle schlägt bei aktiven Fremdschlüsseln fehl, sobald andere Tabellen auf
    sie verweisen. Deshalb sind die Fremdschlüssel nur während der Migration aus (der Schalter
    wirkt nur außerhalb einer Transaktion) und werden danach geprüft.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.connect() as connection:
        driver = connection.connection.driver_connection
        driver.execute("PRAGMA foreign_keys = OFF")  # type: ignore[union-attr]
        try:
            with connection.begin():
                config.attributes["connection"] = connection
                action(config, revision)
                violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError(
                        "Die Migration würde Fremdschlüssel verletzen und wurde abgebrochen."
                    )
        finally:
            driver.execute("PRAGMA foreign_keys = ON")  # type: ignore[union-attr]
