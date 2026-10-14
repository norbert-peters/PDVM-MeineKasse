"""Anwendereinstellungen, z. B. die gespeicherte Sortierung von Tabellen (Vorgabe 2.14)."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from meine_kasse.application.ports import UnitOfWorkFactory
from meine_kasse.domain.errors import ValidationError

_MAX_KEY_LENGTH = 200
_TABLE_PREFIX = "table."


@dataclass(frozen=True, slots=True)
class TableSort:
    """Sortierung einer Tabelle nach genau einer Spalte (Spaltenüberschrift als Kennung)."""

    column: str
    ascending: bool = True


class UserSettingsService:
    """Speichert Einstellungen je Anwender als JSON. Passwörter gehören hier nie hinein."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def get(self, user_id: str, key: str) -> dict[str, Any] | None:
        """Liefert die Einstellung oder `None`, wenn sie fehlt oder nicht lesbar ist."""
        _validate_key(key)
        with self._uow_factory() as uow:
            raw = uow.user_settings.get(user_id, key)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def set(self, user_id: str, key: str, value: Mapping[str, Any]) -> None:
        _validate_key(key)
        with self._uow_factory() as uow:
            uow.user_settings.save(user_id, key, json.dumps(dict(value), ensure_ascii=False))
            uow.commit()

    def remove(self, user_id: str, key: str) -> None:
        _validate_key(key)
        with self._uow_factory() as uow:
            uow.user_settings.delete(user_id, key)
            uow.commit()

    def get_table_sort(self, user_id: str, table_key: str) -> TableSort | None:
        value = self.get(user_id, _TABLE_PREFIX + table_key)
        if value is None:
            return None
        column = value.get("column")
        if not isinstance(column, str) or not column:
            return None
        return TableSort(column=column, ascending=value.get("order") != "desc")

    def save_table_sort(self, user_id: str, table_key: str, sort: TableSort | None) -> None:
        key = _TABLE_PREFIX + table_key
        if sort is None:
            self.remove(user_id, key)
            return
        self.set(
            user_id, key, {"column": sort.column, "order": "asc" if sort.ascending else "desc"}
        )


def _validate_key(key: str) -> None:
    if not key.strip() or len(key) > _MAX_KEY_LENGTH:
        raise ValidationError("Der Schlüssel der Einstellung ist ungültig.")
