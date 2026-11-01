from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from meine_kasse.domain.enums import DocumentType, ReportSource
from meine_kasse.infrastructure.database.base import Base
from meine_kasse.infrastructure.database.models.mixins import (
    IdNameMixin,
    TimestampMixin,
    in_values,
)


class DocumentModel(IdNameMixin, TimestampMixin, Base):
    """PDF-Datei im Dokumentenarchiv. `name` ist der Titel, `file_name` der Dateiname."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("file_name"),
        CheckConstraint(in_values("document_type", DocumentType), name="document_type_valid"),
        CheckConstraint("size_bytes >= 0", name="size_valid"),
    )

    file_name: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(20))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))


class ReportDefinitionModel(IdNameMixin, TimestampMixin, Base):
    """Gespeicherte Auswertung eines Anwenders. Eindeutig je Anwender und Name."""

    __tablename__ = "report_definitions"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        CheckConstraint(in_values("data_source", ReportSource), name="data_source_valid"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    data_source: Mapped[str] = mapped_column(String(30))
    columns_json: Mapped[str] = mapped_column(Text, default="[]")
    filters_json: Mapped[str] = mapped_column(Text, default="[]")
    sort_json: Mapped[str] = mapped_column(Text, default="null")
    grouping_json: Mapped[str] = mapped_column(Text, default="[]")
