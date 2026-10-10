from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from meine_kasse.infrastructure.database.base import Base
from meine_kasse.infrastructure.database.models.mixins import IdNameMixin, TimestampMixin


class AuditLogModel(IdNameMixin, TimestampMixin, Base):
    """Protokoll. `name` ist die Aktion. Enthält keine Passwörter oder Hashes."""

    __tablename__ = "audit_log"

    entity: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(36), default=None)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    old_value: Mapped[str | None] = mapped_column(Text, default=None)
    new_value: Mapped[str | None] = mapped_column(Text, default=None)
