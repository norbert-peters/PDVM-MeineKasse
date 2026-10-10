from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BookingControl:
    """Buchungssteuerung. Es gibt genau einen aktiven Datensatz."""

    id: str
    name: str
    planning_enabled: bool
    current_year: int
    current_month: int
    last_closed_year: int | None = None
    last_closed_month: int | None = None
