"""Buchungsseiten und Wirkung eines Betrags (siehe Architekturvorgabe 2.1, 2.2, 2.4).

Soll = Abfluss/Verbrauch, Haben = Zufluss/Verfügbares, Saldo = Haben - Soll.
Vorzeichen und erfasste Seite werden nie normalisiert oder getauscht.
"""

from dataclasses import dataclass

from meine_kasse.domain.entities.booking import Booking
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


@dataclass(frozen=True, slots=True)
class ActualDelta:
    """Änderung der Ist-Summen einer Kostenstelle in einem Monat (Soll und Haben getrennt)."""

    cost_center_id: str
    year: int
    month: int
    debit_delta_cents: int
    credit_delta_cents: int

    @property
    def movement_delta_cents(self) -> int:
        return self.debit_delta_cents - self.credit_delta_cents


@dataclass(frozen=True, slots=True)
class BudgetDelta:
    """Änderung des wirksamen Jahresansatzes einer Kostenstelle."""

    cost_center_id: str
    year: int
    delta_cents: int


@dataclass(frozen=True, slots=True)
class BookingEffects:
    actuals: tuple[ActualDelta, ...] = ()
    budgets: tuple[BudgetDelta, ...] = ()

    def negated(self) -> "BookingEffects":
        """Die Gegenwirkung, z. B. beim Ändern oder Löschen einer Buchung."""
        return BookingEffects(
            actuals=tuple(
                ActualDelta(
                    delta.cost_center_id,
                    delta.year,
                    delta.month,
                    -delta.debit_delta_cents,
                    -delta.credit_delta_cents,
                )
                for delta in self.actuals
            ),
            budgets=tuple(
                BudgetDelta(delta.cost_center_id, delta.year, -delta.delta_cents)
                for delta in self.budgets
            ),
        )

    def combined(self, other: "BookingEffects") -> "BookingEffects":
        """Summiert zwei Wirkungen. Einträge mit Nettowirkung 0 entfallen."""
        actual_sums: dict[tuple[str, int, int], list[int]] = {}
        for actual in (*self.actuals, *other.actuals):
            entry = actual_sums.setdefault(
                (actual.cost_center_id, actual.year, actual.month), [0, 0]
            )
            entry[0] += actual.debit_delta_cents
            entry[1] += actual.credit_delta_cents
        budget_sums: dict[tuple[str, int], int] = {}
        for budget in (*self.budgets, *other.budgets):
            key = (budget.cost_center_id, budget.year)
            budget_sums[key] = budget_sums.get(key, 0) + budget.delta_cents
        return BookingEffects(
            actuals=tuple(
                ActualDelta(cost_center_id, year, month, debit, credit)
                for (cost_center_id, year, month), (debit, credit) in actual_sums.items()
                if debit or credit
            ),
            budgets=tuple(
                BudgetDelta(cost_center_id, year, delta)
                for (cost_center_id, year), delta in budget_sums.items()
                if delta
            ),
        )


def effects_of(booking: Booking) -> BookingEffects:
    """Wirkung einer Buchung auf Plan-Ist-Werte und Ansatz.

    Die Ist-Werte werden in der Planperiode des Entstehungsdatums fortgeschrieben (Architektur-
    vorgabe 2.11), der Ansatz im Buchungsjahr. Konten haben keine gespeicherte Wirkung, ihr
    Saldo wird aus den Buchungen berechnet. Ansatzumbuchungen berühren nie die Ist-Werte.
    """
    actuals: list[ActualDelta] = []
    budgets: list[BudgetDelta] = []
    for leg in booking.legs:
        if leg.cost_center_id is None:
            continue
        if booking.booking_type is BookingType.BUDGET_TRANSFER:
            budgets.append(
                BudgetDelta(
                    leg.cost_center_id,
                    booking.fiscal_year,
                    balance_effect(leg.side, booking.amount_cents),
                )
            )
        else:
            is_debit = leg.side is Side.DEBIT
            actuals.append(
                ActualDelta(
                    leg.cost_center_id,
                    booking.origin_date.year,
                    booking.origin_date.month,
                    booking.amount_cents if is_debit else 0,
                    0 if is_debit else booking.amount_cents,
                )
            )
    return BookingEffects(tuple(actuals), tuple(budgets))
