"""Planungsregeln (siehe Architekturvorgabe 2.7 und 2.8).

Die Planung wird intern immer als Monatswerte gespeichert. Gleichmäßiges Verteilen ist eine
reine Eingabehilfe. Die Rückstellungen stehen in `reserve_rules`.
"""

from collections.abc import Sequence

from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.value_objects.money import format_euro

MONTHS = range(1, 13)


def distribute_evenly(total_cents: int, months: Sequence[int]) -> dict[int, int]:
    """Teilt einen Betrag gleichmäßig auf Monate. Rundungsreste (Cent) gehen an die ersten Monate,
    sodass die Summe immer dem Betrag entspricht."""
    if total_cents < 0:
        raise ValidationError("Der zu verteilende Betrag darf nicht negativ sein.")
    if not months:
        raise ValidationError("Es ist kein Monat zum Verteilen vorhanden.")
    base, remainder = divmod(total_cents, len(months))
    return {month: base + (1 if index < remainder else 0) for index, month in enumerate(months)}


def check_distribution(effective_budget_cents: int, distributed_cents: int) -> None:
    """Die Summe der Monatsplanwerte darf den wirksamen Jahresansatz nicht übersteigen.

    Ein negativer Ansatz (Haushaltsrest wurde ohne Ansatz weitergegeben) lässt keine Verteilung zu.
    """
    limit = max(0, effective_budget_cents)
    if distributed_cents > limit:
        excess = distributed_cents - limit
        raise ValidationError(
            f"Die Monatsplanung ({format_euro(distributed_cents)}) übersteigt den Jahresansatz "
            f"({format_euro(effective_budget_cents)}) um {format_euro(excess)}."
        )


def check_reserve_distribution(effective_budget_cents: int, reserve_cents: int) -> None:
    """Die Summe der Zuführungen darf den wirksamen Jahresansatz nicht übersteigen."""
    limit = max(0, effective_budget_cents)
    if reserve_cents > limit:
        excess = reserve_cents - limit
        raise ValidationError(
            f"Die Rückstellungen ({format_euro(reserve_cents)}) übersteigen den Jahresansatz "
            f"({format_euro(effective_budget_cents)}) um {format_euro(excess)}."
        )


def validate_plan_amounts(*, base_cents: int, carry_in_cents: int) -> None:
    if base_cents < 0:
        raise ValidationError("Der Haushaltsansatz darf nicht negativ sein.")
    if carry_in_cents < 0:
        raise ValidationError("Der Rückstellungsvortrag darf nicht negativ sein.")


def validate_month_amounts(month: int, plan_cents: int, reserve_plan_cents: int | None) -> None:
    if month not in MONTHS:
        raise ValidationError(f"Ungültiger Monat: {month}.")
    if plan_cents < 0 or (reserve_plan_cents is not None and reserve_plan_cents < 0):
        raise ValidationError(f"Planwerte dürfen nicht negativ sein (Monat {month:02d}).")
