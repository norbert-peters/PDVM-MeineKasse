from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from meine_kasse.infrastructure.database.base import UtcDateTime, new_id, utc_now


class IdNameMixin:
    """Jeder Datensatz hat eine GUID als Primärschlüssel und einen Namen."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), default="")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


def in_values(column: str, enum_type: type[StrEnum]) -> str:
    """SQL-Bedingung, die eine Spalte auf die Werte einer Aufzählung beschränkt."""
    return _in_list(column, (member.value for member in enum_type))


def _in_list(column: str, values: Iterable[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"
