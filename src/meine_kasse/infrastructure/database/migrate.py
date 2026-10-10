from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def upgrade_database(engine: Engine, revision: str = "head") -> None:
    """Bringt die Datenbank auf den gewünschten Schemastand."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
