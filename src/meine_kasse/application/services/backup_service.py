"""Datensicherung: Kopie der gesamten Datenbank und des Dokumentenverzeichnisses."""

import logging
import shutil
from pathlib import Path

from meine_kasse.application.ports import DatabaseBackup, Today, local_today
from meine_kasse.domain.errors import ValidationError

logger = logging.getLogger("meine_kasse.backup")
DOCUMENTS_SUFFIX = "_Dokumente"


class BackupService:
    def __init__(
        self,
        backup: DatabaseBackup,
        database_file: Path,
        today: Today = local_today,
        documents_dir: Path | None = None,
    ) -> None:
        self._backup = backup
        self._database_file = database_file
        self._today = today
        self._documents_dir = documents_dir

    def suggested_file_name(self) -> str:
        return f"meine_kasse_{self._today():%Y-%m-%d}.sqlite"

    @staticmethod
    def documents_target(database_target: Path) -> Path:
        """Ordner der gesicherten Dokumente neben der Sicherungsdatei."""
        return database_target.with_name(database_target.stem + DOCUMENTS_SUFFIX)

    def create_backup(self, target: Path) -> Path:
        """Schreibt eine Sicherung. Eine vorhandene Zieldatei wird ersetzt.

        Die Dokumente werden in den Ordner `<Name>_Dokumente` neben der Datei kopiert.
        """
        if target.suffix.lower() != ".sqlite":
            target = target.with_suffix(".sqlite")
        if target.resolve() == self._database_file.resolve():
            raise ValidationError("Die Sicherung darf nicht die laufende Datenbank überschreiben.")
        documents_target = self.documents_target(target)
        documents = self._documents_dir
        if documents is not None and (
            documents.resolve() == documents_target.resolve()
            or documents.resolve() in (target.resolve().parent, *target.resolve().parents)
        ):
            raise ValidationError(
                "Die Sicherung darf nicht im Dokumentenverzeichnis liegen. "
                "Bitte einen anderen Ordner wählen."
            )
        self._backup.backup_to(target)
        if documents is not None and documents.is_dir():
            if documents_target.exists():
                shutil.rmtree(documents_target)
            shutil.copytree(documents, documents_target)
        logger.info("Datensicherung erstellt: %s", target)
        return target
