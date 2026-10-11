"""Datensicherung: Kopie der gesamten Datenbank in eine Datei."""

import logging
from pathlib import Path

from meine_kasse.application.ports import DatabaseBackup, Today, local_today
from meine_kasse.domain.errors import ValidationError

logger = logging.getLogger("meine_kasse.backup")


class BackupService:
    def __init__(
        self, backup: DatabaseBackup, database_file: Path, today: Today = local_today
    ) -> None:
        self._backup = backup
        self._database_file = database_file
        self._today = today

    def suggested_file_name(self) -> str:
        return f"meine_kasse_{self._today():%Y-%m-%d}.sqlite"

    def create_backup(self, target: Path) -> Path:
        """Schreibt eine Sicherung. Eine vorhandene Zieldatei wird ersetzt."""
        if target.suffix.lower() != ".sqlite":
            target = target.with_suffix(".sqlite")
        if target.resolve() == self._database_file.resolve():
            raise ValidationError("Die Sicherung darf nicht die laufende Datenbank überschreiben.")
        self._backup.backup_to(target)
        logger.info("Datensicherung erstellt: %s", target)
        return target
