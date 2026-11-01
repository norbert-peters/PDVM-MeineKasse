"""PDF-Ausgabe und Dokumentenarchiv (Architekturvorgabe 2.14).

Jede erzeugte PDF-Datei liegt im Dokumentenverzeichnis und wird in `documents` registriert
(Name, Art, Ersteller, Zeitpunkt, Größe, SHA-256). Archivierte Dateien werden nie überschrieben.
"""

import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from meine_kasse.application.ports import Clock, PdfRenderer, UnitOfWorkFactory, utc_now
from meine_kasse.application.reporting.pdf_model import PdfTable
from meine_kasse.domain.entities import AuditEntry, Document
from meine_kasse.domain.enums import DocumentType
from meine_kasse.domain.errors import NotFoundError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.services.document_rules import build_file_name

logger = logging.getLogger("meine_kasse.documents")
_MAX_TITLE_LENGTH = 200
_HASH_BLOCK = 1024 * 1024


class DocumentState(StrEnum):
    OK = "OK"
    MISSING = "MISSING"
    CHANGED = "CHANGED"


@dataclass(frozen=True, slots=True)
class DocumentView:
    id: str
    name: str
    file_name: str
    document_type: DocumentType
    created_by: str
    created_at: datetime
    size_bytes: int
    sha256: str
    exists: bool


class DocumentService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        renderer: PdfRenderer,
        directory: Path,
        clock: Clock = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._renderer = renderer
        self._directory = directory
        self._clock = clock

    @property
    def directory(self) -> Path:
        return self._directory

    def create_pdf(
        self,
        table: PdfTable,
        *,
        document_type: DocumentType,
        suffix: str = "",
        actor_id: str,
    ) -> DocumentView:
        """Erzeugt das PDF im Dokumentenverzeichnis und registriert es im Archiv."""
        created_at = self._clock()
        file_name = build_file_name(created_at.astimezone(), table.title, suffix)
        self._directory.mkdir(parents=True, exist_ok=True)
        target = self._free_path(file_name)
        try:
            self._renderer.render(table, target)
            document = Document(
                id=new_id(),
                name=table.title[:_MAX_TITLE_LENGTH],
                file_name=target.name,
                document_type=document_type,
                created_by_user_id=actor_id,
                size_bytes=target.stat().st_size,
                sha256=_sha256(target),
                created_at=created_at,
            )
            with self._uow_factory() as uow:
                uow.documents.add(document)
                uow.audit.add(
                    AuditEntry(
                        name="document.create",
                        entity="documents",
                        entity_id=document.id,
                        user_id=actor_id,
                        new_value=json.dumps(
                            {"file_name": document.file_name, "type": document_type.value},
                            ensure_ascii=False,
                        ),
                    )
                )
                uow.commit()
                users = {user.id: user.display_name for user in uow.users.list_all()}
        except Exception:
            target.unlink(missing_ok=True)
            raise
        logger.info("PDF erzeugt: %s", target.name)
        return self._view(document, users.get(actor_id, ""))

    def list_documents(self) -> Sequence[DocumentView]:
        with self._uow_factory() as uow:
            documents = uow.documents.list_all()
            users = {user.id: user.display_name for user in uow.users.list_all()}
        return [self._view(item, users.get(item.created_by_user_id, "")) for item in documents]

    def path_of(self, document_id: str) -> Path:
        """Pfad der archivierten Datei. Fehlt sie, wird das gemeldet."""
        document = self._get(document_id)
        path = self._directory / document.file_name
        if not path.is_file():
            raise NotFoundError(
                f"Die Datei '{document.file_name}' fehlt im Dokumentenverzeichnis "
                f"({self._directory})."
            )
        return path

    def verify(self, document_id: str) -> DocumentState:
        """Vergleicht die Datei mit Größe und SHA-256 aus dem Archiv."""
        document = self._get(document_id)
        path = self._directory / document.file_name
        if not path.is_file():
            return DocumentState.MISSING
        if path.stat().st_size != document.size_bytes or _sha256(path) != document.sha256:
            return DocumentState.CHANGED
        return DocumentState.OK

    # Intern

    def _get(self, document_id: str) -> Document:
        with self._uow_factory() as uow:
            document = uow.documents.get(document_id)
        if document is None:
            raise NotFoundError("Das Dokument wurde nicht gefunden.")
        return document

    def _view(self, document: Document, created_by: str) -> DocumentView:
        return DocumentView(
            id=document.id,
            name=document.name,
            file_name=document.file_name,
            document_type=document.document_type,
            created_by=created_by,
            created_at=document.created_at,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            exists=(self._directory / document.file_name).is_file(),
        )

    def _free_path(self, file_name: str) -> Path:
        """Ein vorhandener Dateiname wird nie überschrieben, sondern nummeriert."""
        candidate = self._directory / file_name
        stem, suffix = candidate.stem, candidate.suffix
        counter = 2
        while candidate.exists():
            candidate = self._directory / f"{stem}_{counter}{suffix}"
            counter += 1
        return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(_HASH_BLOCK):
            digest.update(block)
    return digest.hexdigest()
