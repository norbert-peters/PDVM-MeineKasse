"""Liquiditätsplanung je Planmonat (Architekturvorgabe 2.16).

Je Monat stehen die erwarteten Einnahmen dem Liquiditätsbedarf gegenüber. Der Bedarf besteht aus
den Zuführungen zu den Rückstellungen und den Zahlungen, die die Rückstellung nicht deckt. Eine
Zahlung, die aus der Rückstellung entlastet wird, belastet die Liquidität nicht noch einmal,
denn das Geld wurde mit der Zuführung zurückgelegt. Alle Beträge sind ganzzahlige Cent.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from meine_kasse.domain.enums import IncomeMode
from meine_kasse.domain.services.planning_rules import MONTHS


def expected_income(mode: IncomeMode, plan_cents: int, realized_cents: int, *, closed: bool) -> int:
    """Erwartete Einnahme eines Monats in der Liquiditätsplanung.

    Abgeschlossene Monate und Einnahmen im Modus `ACTUAL` zählen nur mit dem Ist (Vorsicht). Im
    Modus `PLAN` gilt in offenen Monaten der Plan, mindestens aber die gebuchte Einnahme.
    """
    realized = max(0, realized_cents)
    if closed or mode is IncomeMode.ACTUAL:
        return realized
    return max(plan_cents, realized)


def uncovered_payments(
    effective_movement: Mapping[int, int], release: Mapping[int, int]
) -> dict[int, int]:
    """Zahlungen je Monat, die nicht aus der Rückstellung entlastet werden (nie negativ)."""
    return {
        month: max(0, effective_movement.get(month, 0) - release.get(month, 0)) for month in MONTHS
    }


@dataclass(frozen=True, slots=True)
class LiquidityMonth:
    month: int
    income_cents: int
    reserve_cents: int
    payment_cents: int
    is_closed: bool
    # Nur zur Anzeige: alle Zahlungen vom Bankkonto, auch die aus Rückstellungen entlasteten.
    bank_outflow_cents: int = 0
    # Nur zur Anzeige: Rückfluss, also die aus den Rückstellungen entlasteten Zahlungen.
    reserve_release_cents: int = 0

    @property
    def reserve_movement_cents(self) -> int:
        """Nur zur Anzeige: Zuführung − Rückfluss. Positiv heißt: Geld wird zurückgelegt."""
        return self.reserve_cents - self.reserve_release_cents

    @property
    def need_cents(self) -> int:
        return self.reserve_cents + self.payment_cents

    @property
    def balance_cents(self) -> int:
        """Einnahmen − Bedarf. Negativ heißt: Die Einnahmen des Monats reichen nicht."""
        return self.income_cents - self.need_cents


def cumulative_balances(months: Collection[LiquidityMonth]) -> dict[int, int]:
    """Überschuss bzw. Fehlbetrag, fortlaufend über die Monate des Jahres aufsummiert."""
    running = 0
    balances: dict[int, int] = {}
    for item in sorted(months, key=lambda month: month.month):
        running += item.balance_cents
        balances[item.month] = running
    return balances
