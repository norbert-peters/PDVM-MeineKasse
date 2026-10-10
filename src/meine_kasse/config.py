"""Pfade und Einstellungen der Anwendung."""

import os
from pathlib import Path

DATABASE_ENV_VARIABLE = "MEINE_KASSE_DB"


def database_path() -> Path:
    """Speicherort der SQLite-Datei. Standard ist der Anwenderdatenordner, nie der Quellcode."""
    override = os.environ.get(DATABASE_ENV_VARIABLE)
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "MeineKasse" / "meine_kasse.sqlite"
