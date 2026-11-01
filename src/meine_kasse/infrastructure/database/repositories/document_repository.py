from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import Document
from meine_kasse.domain.enums import DocumentType
from meine_kasse.infrastructure.database.models import DocumentModel


def _to_entity(model: DocumentModel) -> Document:
    return Document(
        id=model.id,
        name=model.name,
        file_name=model.file_name,
        document_type=DocumentType(model.document_type),
        created_by_user_id=model.created_by_user_id,
        size_bytes=model.size_bytes,
        sha256=model.sha256,
        created_at=model.created_at,
    )


class SqlDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, document: Document) -> None:
        self._session.add(
            DocumentModel(
                id=document.id,
                name=document.name,
                file_name=document.file_name,
                document_type=document.document_type.value,
                created_by_user_id=document.created_by_user_id,
                size_bytes=document.size_bytes,
                sha256=document.sha256,
                created_at=document.created_at,
            )
        )
        self._session.flush()

    def get(self, document_id: str) -> Document | None:
        model = self._session.get(DocumentModel, document_id)
        return None if model is None else _to_entity(model)

    def list_all(self) -> Sequence[Document]:
        statement = select(DocumentModel).order_by(
            DocumentModel.created_at.desc(), DocumentModel.file_name
        )
        return [_to_entity(model) for model in self._session.scalars(statement)]
