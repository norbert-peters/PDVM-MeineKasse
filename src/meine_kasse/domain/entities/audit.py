from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Protokolleintrag. `old_value`/`new_value` enthalten nie Passwörter oder Hashes."""

    name: str
    entity: str
    entity_id: str | None
    user_id: str | None
    old_value: str | None = None
    new_value: str | None = None
