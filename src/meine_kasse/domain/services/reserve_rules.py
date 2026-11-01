"""Rückstellungen je Kostenstelle (Architekturvorgabe 2.12).

Eine Rückstellung ist ein virtuelles Konto der Kostenstelle. Sie wird nicht gebucht, sondern aus
Plan und Ist berechnet (Soll = Bildung/Zuführung, Haben = Entlastung, Bestand = Soll - Haben):

- Zuführung: je Monat gebildete Rückstellung (`reserve_plan_cents`).
- Planentlastung: die direkt geplanten Zahlungen (`plan_cents`) im Zahlungsmonat. Sie gelten in
  offenen Monaten, bis die Ist-Zahlung sie übersteigt oder der Monat abgeschlossen ist.
- Entlastung (ist): Ist-Bewegung des Monats, soweit Bestand vorhanden ist.
- Vortrag: Bestand zum Jahresende nach Plan und Ist, Anfangsbestand des Folgejahres.

Der Bestand ist nie negativ. Alle Beträge sind ganzzahlige Cent.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from meine_kasse.domain.services.planning_rules import MONTHS, distribute_evenly


def is_directly_planned(plan_cents: Mapping[int, int]) -> bool:
    """In allen zwölf Monaten ist eine Zahlung geplant: dann gibt es keine Rückstellungen."""
    return all(plan_cents.get(month, 0) > 0 for month in MONTHS)


def _take_evenly(values: Mapping[int, int], months: Sequence[int], total: int) -> dict[int, int]:
    """Nimmt höchstens `total` gleichmäßig aus den Monaten, kein Monat fällt unter 0."""
    taken = dict.fromkeys(months, 0)
    remaining = total
    active = [month for month in months if values[month] > 0]
    while remaining > 0 and active:
        share, extra = divmod(remaining, len(active))
        progress = 0
        for index, month in enumerate(active):
            wanted = share + (1 if index < extra else 0)
            take = min(values[month] - taken[month], wanted)
            taken[month] += take
            progress += take
        remaining -= progress
        active = [month for month in active if values[month] - taken[month] > 0]
    return taken


def plan_balances(
    carry_in_cents: int, reserve_plan: Mapping[int, int], plan_cents: Mapping[int, int]
) -> dict[int, int]:
    """Planbestand nach jedem Monat: Vortrag + Zuführungen - geplante Zahlungen (kumuliert)."""
    running = carry_in_cents
    balances: dict[int, int] = {}
    for month in MONTHS:
        running += reserve_plan.get(month, 0) - plan_cents.get(month, 0)
        balances[month] = running
    return balances


def plan_shortfalls(
    carry_in_cents: int, reserve_plan: Mapping[int, int], plan_cents: Mapping[int, int]
) -> dict[int, int]:
    """Monate, in denen die Rückstellung die geplante Zahlung nicht deckt (Fehlbetrag in Cent).

    Wie bei der Entlastung gibt es keinen negativen Bestand: Ein Fehlbetrag wird in dem Monat
    gemeldet, in dem er entsteht, und nicht gegen spätere Zuführungen aufgerechnet. Bei Planung
    in allen Monaten gibt es keine Rückstellung und damit keinen Fehlbetrag.
    """
    if is_directly_planned(plan_cents):
        return {}
    return compute_reserve_year(carry_in_cents, reserve_plan, plan_cents).shortfall


def distribute_reserve(
    *,
    budget_cents: int,
    carry_in_cents: int,
    plan_cents: Mapping[int, int],
    fixed: Mapping[int, int],
    free_months: Sequence[int],
    to_payment_targets: bool = False,
) -> dict[int, int]:
    """Verteilt den Jahresansatz maschinell als Zuführung auf die freien Monate.

    `fixed` enthält die Zuführungen gesperrter (abgeschlossener oder manuell gesetzter) Monate,
    `free_months` die Monate, die berechnet werden dürfen.

    1. Sind alle Monate direkt geplant, bleiben die freien Monate bei 0.
    2. Sonst wird der noch nicht gebundene Ansatz gleichmäßig auf die freien Monate verteilt
       (Rundungsrest an die ersten Monate). Geplante Zahlungen ändern daran nichts.
    3. Nur mit `to_payment_targets`: Deckt Vortrag + Zuführung bis zum Zahlungsmonat die
       geplanten Zahlungen nicht, werden die Zuführungen vor der Zahlung erhöht, und zwar in den
       freien Monaten seit der letzten Deckungslücke. Die Summe bleibt gleich, weil die Monate
       nach der Zahlung entsprechend weniger erhalten. Nichts wird negativ, die Summe übersteigt
       den Ansatz nie.
    """
    free = sorted(set(free_months))
    reserve = {month: fixed.get(month, 0) for month in MONTHS}
    for month in free:
        reserve[month] = 0
    if not free or is_directly_planned(plan_cents):
        return reserve

    available = max(0, budget_cents - sum(reserve.values()))
    for month, cents in distribute_evenly(available, free).items():
        reserve[month] = cents
    if not to_payment_targets:
        return reserve

    last_covered = 0
    running_plan = 0
    for month in MONTHS:
        running_plan += plan_cents.get(month, 0)
        cumulative = sum(reserve[m] for m in MONTHS if m <= month)
        need = running_plan - carry_in_cents - cumulative
        if need <= 0:
            continue
        receivers = [f for f in free if last_covered < f <= month] or [
            f for f in free if f <= month
        ]
        donors = [f for f in free if f > month]
        if not receivers or not donors:
            continue
        taken = _take_evenly(reserve, donors, need)
        moved = sum(taken.values())
        if moved == 0:
            continue
        for donor, cents in taken.items():
            reserve[donor] -= cents
        for receiver, cents in distribute_evenly(moved, receivers).items():
            reserve[receiver] += cents
        last_covered = month
    return reserve


@dataclass(frozen=True, slots=True)
class ReserveYear:
    """Ergebnis der Rückstellungsrechnung eines Jahres (Beträge in Cent)."""

    release: dict[int, int]
    shortfall: dict[int, int]
    balance: dict[int, int]
    carry_out_cents: int


def compute_reserve_year(
    carry_in_cents: int, reserve_plan: Mapping[int, int], movement: Mapping[int, int]
) -> ReserveYear:
    """Entlastung der Rückstellung durch die Ist-Bewegung, je Monat aus der Monatssumme.

    - Eine positive Bewegung entlastet bis zum verfügbaren Bestand (Vortrag + Zuführungen bis
      einschließlich des Monats - bisherige Entlastungen). Der Rest ist der Fehlbetrag.
    - Eine negative Bewegung (Erstattung) gibt höchstens die bisherige Entlastung zurück.
    - Der Bestand ist dadurch nie negativ. Die Rechnung hängt nur von Monatssummen ab, nicht von
      der Reihenfolge einzelner Buchungen.
    """
    released_so_far = 0
    supplied = carry_in_cents
    release: dict[int, int] = {}
    shortfall: dict[int, int] = {}
    balance: dict[int, int] = {}
    for month in MONTHS:
        supplied += reserve_plan.get(month, 0)
        moved = movement.get(month, 0)
        if moved > 0:
            available = max(0, supplied - released_so_far)
            relief = min(moved, available)
            if moved > relief:
                shortfall[month] = moved - relief
        elif moved < 0:
            relief = max(moved, -released_so_far)
        else:
            relief = 0
        release[month] = relief
        released_so_far += relief
        balance[month] = supplied - released_so_far
    return ReserveYear(release, shortfall, balance, balance[MONTHS[-1]])


def effective_movement(
    plan_cents: Mapping[int, int], movement: Mapping[int, int], closed_months: Collection[int]
) -> dict[int, int]:
    """Zahlung je Monat, die die Rückstellung im Ausblick entlastet.

    Abgeschlossene Monate zählen nur mit der Ist-Bewegung. In offenen Monaten gilt die geplante
    Zahlung, solange das Ist sie nicht übersteigt. So zeigt der Vortrag den Betrag, der nach
    Plan tatsächlich angespart ist, und die Ist-Zahlung gleicht den Plan beim Zahlen ab.
    """
    return {
        month: (
            movement.get(month, 0)
            if month in closed_months or movement.get(month, 0) < 0
            else max(plan_cents.get(month, 0), movement.get(month, 0))
        )
        for month in MONTHS
    }


def compute_reserve_outlook(
    carry_in_cents: int,
    reserve_plan: Mapping[int, int],
    plan_cents: Mapping[int, int],
    movement: Mapping[int, int],
    closed_months: Collection[int],
) -> ReserveYear:
    """Rückstellung nach Plan: wie `compute_reserve_year`, aber offene Monate mit Planzahlung."""
    return compute_reserve_year(
        carry_in_cents, reserve_plan, effective_movement(plan_cents, movement, closed_months)
    )
