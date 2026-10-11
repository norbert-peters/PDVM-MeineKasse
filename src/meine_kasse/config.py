"""Pfade und Einstellungen der Anwendung."""

import os
from pathlib import Path

DATABASE_ENV_VARIABLE = "MEINE_KASSE_DB"
DATABASE_FILE_NAME = "meine_kasse.sqlite"


def data_dir() -> Path:
    """Ordner für Datenbank und Protokolle. Er liegt nie im Programmverzeichnis, damit ein
    Update der Anwendung die Daten nicht berührt."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "MeineKasse"


def database_path() -> Path:
    """Speicherort der SQLite-Datei. Mit `MEINE_KASSE_DB` kann ein anderer Pfad gesetzt werden."""
    override = os.environ.get(DATABASE_ENV_VARIABLE)
    if override:
        return Path(override)
    return data_dir() / DATABASE_FILE_NAME


def log_dir() -> Path:
    """Ordner der Protokolldatei. Liegt neben der Datenbank, wenn diese überschrieben wurde."""
    if os.environ.get(DATABASE_ENV_VARIABLE):
        return database_path().parent / "logs"
    return data_dir() / "logs"
