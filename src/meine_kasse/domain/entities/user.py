from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class User:
    """Anwender. `name` ist der Anmeldename. Hashes erscheinen nie in der Textdarstellung."""

    id: str
    name: str
    last_name: str
    first_name: str
    address: str
    password_hash: str = field(repr=False)
    initial_password_hash: str | None = field(repr=False)
    must_change_password: bool
    password_changed_at: datetime | None
    is_active: bool = True

    @property
    def display_name(self) -> str:
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.name
