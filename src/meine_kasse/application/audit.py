"""Hilfsfunktion für Audit-Einträge bei Änderungen."""

import json
from collections.abc import Collection
from typing import Any

PROTECTED_PLACEHOLDER = "(geändert)"


def describe_changes(
    old: Any,
    new: Any,
    fields: Collection[str],
    *,
    protected: Collection[str] = (),
) -> tuple[str, str] | None:
    """Liefert die geänderten Felder als JSON (alt, neu) oder `None`, wenn nichts geändert wurde.

    Werte geschützter Felder (z. B. IBAN, Anschrift) werden nie protokolliert.
    """
    old_values: dict[str, Any] = {}
    new_values: dict[str, Any] = {}
    for field in fields:
        before, after = getattr(old, field), getattr(new, field)
        if before == after:
            continue
        hidden = field in protected
        old_values[field] = PROTECTED_PLACEHOLDER if hidden else before
        new_values[field] = PROTECTED_PLACEHOLDER if hidden else after
    if not new_values:
        return None
    return (
        json.dumps(old_values, ensure_ascii=False, default=str),
        json.dumps(new_values, ensure_ascii=False, default=str),
    )
