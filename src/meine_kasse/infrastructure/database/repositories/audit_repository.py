from sqlalchemy.orm import Session

from meine_kasse.domain.entities import AuditEntry
from meine_kasse.infrastructure.database.models import AuditLogModel


class SqlAuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entry: AuditEntry) -> None:
        self._session.add(
            AuditLogModel(
                name=entry.name,
                entity=entry.entity,
                entity_id=entry.entity_id,
                user_id=entry.user_id,
                old_value=entry.old_value,
                new_value=entry.new_value,
            )
        )
        self._session.flush()
