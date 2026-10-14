from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from meine_kasse.infrastructure.database.base import Base
from meine_kasse.infrastructure.database.models.mixins import IdNameMixin, TimestampMixin


class UserSettingModel(IdNameMixin, TimestampMixin, Base):
    """Einstellung eines Anwenders. `name` ist der Schlüssel, z. B. `table.bookings`."""

    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    value_json: Mapped[str] = mapped_column(Text, default="{}")
