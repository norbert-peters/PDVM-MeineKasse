from dataclasses import dataclass
from datetime import date

from meine_kasse.domain.enums import BookingType, Side


@dataclass(frozen=True, slots=True)
class BookingLeg:
    """Buchungsstelle. Genau eines von `cost_center_id` und `account_id` ist gesetzt."""

    position: int
    side: Side
    cost_center_id: str | None
    account_id: str | None


@dataclass(frozen=True, slots=True)
class Booking:
    """Buchung mit vorzeichenbehaftetem Betrag in Cent und genau zwei Stellen."""

    id: str
    name: str
    origin_date: date
    booking_date: date
    booking_type: BookingType
    entry_side: Side
    amount_cents: int
    merchant: str
    booking_text: str
    reversal_of_id: str | None
    fiscal_year: int
    fiscal_month: int
    created_by_user_id: str
    legs: tuple[BookingLeg, BookingLeg]
    # Gemeinsame GUID der beiden Buchungssätze einer Umbuchung, sonst leer
    transfer_id: str | None = None
