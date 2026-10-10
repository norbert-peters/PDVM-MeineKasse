"""Planungsregeln (siehe Architekturvorgabe 2.7 und 2.8).

Die Planung wird intern immer als Monatswerte gespeichert. Gleichmäßige und quartalsweise
Verteilung sind reine Eingabehilfen.
"""

from collections.abc import Collection, Mapping, Sequence

from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.value_objects.money import format_euro

MONTHS = range(1, 13)
QUARTERS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}


def distribute_evenly(total_cents: int, months: Sequence[int]) -> dict[int, int]:
    """Teilt einen Betrag gleichmäßig auf Monate. Rundungsreste (Cent) gehen an die ersten Monate,
    sodass die Summe immer dem Betrag entspricht."""
    if total_cents < 0:
        raise ValidationError("Der zu verteilende Betrag darf nicht negativ sein.")
    if not months:
        raise ValidationError("Es ist kein Monat zum Verteilen vorhanden.")
    base, remainder = divmod(total_cents, len(months))
    return {month: base + (1 if index < remainder else 0) for index, month in enumerate(months)}


def distribute_quarters(
    quarter_cents: Mapping[int, int], open_months: Collection[int]
) -> dict[int, int]:
    """Teilt je Quartal einen Betrag gleichmäßig auf dessen offene Monate.

    Ein Quartalsbetrag ungleich 0 ist nur möglich, wenn das Quartal mindestens einen
    offenen Monat besitzt.
    """
    result: dict[int, int] = {}
    for quarter, cents in quarter_cents.items():
        months = [month for month in QUARTERS[quarter] if month in open_months]
        if not months:
            if cents:
                raise ValidationError(
                    f"Im Quartal {quarter} sind alle Monate abgeschlossen, "
                    "dort kann nichts mehr geplant werden."
                )
            continue
        result.update(distribute_evenly(cents, months))
    return result


def check_distribution(effective_budget_cents: int, distributed_cents: int) -> None:
    """Die Summe der Monatsplanwerte darf den wirksamen Jahresansatz nicht übersteigen."""
    if effective_budget_cents < 0:
        raise ValidationError("Der wirksame Jahresansatz darf nicht negativ sein.")
    if distributed_cents > effective_budget_cents:
        excess = distributed_cents - effective_budget_cents
        raise ValidationError(
            f"Die Monatsplanung ({format_euro(distributed_cents)}) übersteigt den Jahresansatz "
            f"({format_euro(effective_budget_cents)}) um {format_euro(excess)}."
        )


def validate_plan_amounts(*, base_cents: int, carry_in_cents: int, carry_out_cents: int) -> None:
    if base_cents < 0:
        raise ValidationError("Der Haushaltsansatz darf nicht negativ sein.")
    if carry_in_cents < 0 or carry_out_cents < 0:
        raise ValidationError("Rückstellungsüberträge dürfen nicht negativ sein.")


def validate_month_amounts(month: int, plan_cents: int, reserve_plan_cents: int) -> None:
    if month not in MONTHS:
        raise ValidationError(f"Ungültiger Monat: {month}.")
    if plan_cents < 0 or reserve_plan_cents < 0:
        raise ValidationError(f"Planwerte dürfen nicht negativ sein (Monat {month:02d}).")
