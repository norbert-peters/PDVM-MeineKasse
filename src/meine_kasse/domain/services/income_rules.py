"""Einnahmen-Kostenstellen (siehe Architekturvorgabe 2.15).

Eine Einnahme wird nicht als Ansatz geführt, sondern geplant (erwartete Einnahme je Monat) und
gebucht (Haben). Sie wird erst durch eine Ansatzumbuchung auf eine Kostenstelle mit Plan zum
Ansatz. Je Einnahmenstelle legt der Modus fest, wie viel davon weitergegeben werden darf:

- `PLAN`: der Jahresplan, mindestens aber die bereits gebuchte Einnahme (z. B. Rente).
- `ACTUAL`: nur die bereits gebuchte Einnahme (z. B. Zinsen, Orgelspiel).

Die Weitergabe steht als negativer `budget_transfer_cents` im Jahresplan der Einnahmenstelle.
Alle Beträge sind ganzzahlige Cent.
"""

from dataclasses import dataclass

from meine_kasse.domain.enums import IncomeMode
from meine_kasse.domain.errors import BudgetExceededError
from meine_kasse.domain.value_objects.money import format_euro


@dataclass(frozen=True, slots=True)
class IncomePosition:
    """Stand einer Einnahmenstelle im Jahr (Cent)."""

    mode: IncomeMode
    planned_cents: int
    realized_cents: int
    passed_on_cents: int = 0

    @property
    def available_cents(self) -> int:
        """Höchstbetrag, der insgesamt weitergegeben werden darf."""
        realized = max(0, self.realized_cents)
        if self.mode is IncomeMode.PLAN:
            return max(self.planned_cents, realized)
        return realized

    @property
    def free_cents(self) -> int:
        """Noch nicht weitergegebener, verfügbarer Betrag."""
        return max(0, self.available_cents - self.passed_on_cents)

    @property
    def open_expected_cents(self) -> int:
        """Noch erwartete Einnahme: Plan abzüglich Ist, nie negativ."""
        return max(0, self.planned_cents - max(0, self.realized_cents))


def passed_on_cents(budget_transfer_cents: int) -> int:
    """Weitergegebener Betrag aus dem Ansatzkonto der Einnahmenstelle (immer ≥ 0)."""
    return max(0, -budget_transfer_cents)


def check_pass_on(position: IncomePosition, budget_delta_cents: int) -> None:
    """Prüft eine Ansatzumbuchung: Weitergabe nur bis zum verfügbaren Betrag."""
    if budget_delta_cents >= 0:
        return
    after = position.passed_on_cents - budget_delta_cents
    if after > position.available_cents:
        raise BudgetExceededError(
            "Die Einnahme ist nicht in dieser Höhe verfügbar: Es können höchstens "
            f"{format_euro(position.free_cents)} umgebucht werden ({_basis(position)}).",
            after - position.available_cents,
        )


def check_coverage(position: IncomePosition, *, reason: str) -> None:
    """Der weitergegebene Betrag muss durch Plan bzw. Ist gedeckt bleiben."""
    if position.passed_on_cents > position.available_cents:
        shortfall = position.passed_on_cents - position.available_cents
        raise BudgetExceededError(
            f"{reason} Es sind bereits {format_euro(position.passed_on_cents)} auf andere "
            f"Kostenstellen umgebucht, verfügbar bleiben nur "
            f"{format_euro(position.available_cents)}"
            f" ({_basis(position)}). Zuerst die Umbuchung zurücknehmen.",
            shortfall,
        )


def _basis(position: IncomePosition) -> str:
    if position.mode is IncomeMode.PLAN:
        return "nach Plan, mindestens die gebuchte Einnahme"
    return "nur die gebuchte Einnahme"
