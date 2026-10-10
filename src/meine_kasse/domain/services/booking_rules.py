"""Buchungsseiten und Wirkung eines Betrags (siehe Architekturvorgabe 2.1, 2.2, 2.4).

Soll = Abfluss/Verbrauch, Haben = Zufluss/Verfügbares, Saldo = Haben - Soll.
Vorzeichen und erfasste Seite werden nie normalisiert oder getauscht.
"""

from dataclasses import dataclass

from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class Stelle:
    """Konto oder Kostenstelle, auf die gebucht wird."""

    kind: ObjectKind
    id: str


@dataclass(frozen=True, slots=True)
class BookingLegSpec:
    position: int
    side: Side
    stelle: Stelle


_LEADING_AND_SECOND_KIND = {
    BookingType.COST_CENTER_TO_ACCOUNT: (ObjectKind.COST_CENTER, ObjectKind.ACCOUNT),
    BookingType.ACCOUNT_TO_ACCOUNT: (ObjectKind.ACCOUNT, ObjectKind.ACCOUNT),
    BookingType.BUDGET_TRANSFER: (ObjectKind.COST_CENTER, ObjectKind.COST_CENTER),
}

_SAME_SIDE_TYPES = frozenset({BookingType.COST_CENTER_TO_ACCOUNT})


def validate_amount(amount_cents: int) -> None:
    if amount_cents == 0:
        raise ValidationError("Der Betrag darf nicht 0 sein.")


def opposite(side: Side) -> Side:
    return Side.CREDIT if side is Side.DEBIT else Side.DEBIT


def build_legs(
    booking_type: BookingType,
    entry_side: Side,
    leading: Stelle,
    second: Stelle,
) -> tuple[BookingLegSpec, BookingLegSpec]:
    """Leitet die beiden Buchungsstellen aus Buchungsart und Erfassungsseite ab.

    Ist-Buchung: beide Stellen auf der Erfassungsseite (gleichgerichtet).
    Konto -> Konto und Ansatzumbuchung: zweite Stelle gegenläufig.
    """
    expected_leading, expected_second = _LEADING_AND_SECOND_KIND[booking_type]
    if leading.kind is not expected_leading or second.kind is not expected_second:
        raise ValidationError("Die gewählten Stellen passen nicht zur Buchungsart.")
    if leading == second:
        raise ValidationError("Die beiden Stellen einer Buchung müssen verschieden sein.")

    second_side = entry_side if booking_type in _SAME_SIDE_TYPES else opposite(entry_side)
    return (
        BookingLegSpec(position=1, side=entry_side, stelle=leading),
        BookingLegSpec(position=2, side=second_side, stelle=second),
    )


def balance_effect(side: Side, amount_cents: int) -> int:
    """Wirkung auf den Saldo (Haben - Soll). Bei Ansatzumbuchungen ist das die Ansatzänderung."""
    return amount_cents if side is Side.CREDIT else -amount_cents


def movement_effect(side: Side, amount_cents: int) -> int:
    """Wirkung auf die Ist-Bewegung (Soll - Haben)."""
    return -balance_effect(side, amount_cents)
