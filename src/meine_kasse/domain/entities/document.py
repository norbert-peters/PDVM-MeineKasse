from dataclasses import dataclass
from datetime import datetime

from meine_kasse.domain.enums import DocumentType


@dataclass(frozen=True, slots=True)
class Document:
    """Eintrag im Dokumentenarchiv. `name` ist der lesbare Titel, `file_name` der Dateiname."""

    id: str
    name: str
    file_name: str
    document_type: DocumentType
    created_by_user_id: str
    size_bytes: int
    sha256: str
    created_at: datetime
