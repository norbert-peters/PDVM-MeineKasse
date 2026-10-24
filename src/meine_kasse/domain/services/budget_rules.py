"""Ansatzsperre und Ansatzumbuchung (siehe Architekturvorgabe 2.7)."""

from dataclasses import dataclass

from meine_kasse.domain.enums import CostCenterKind
from meine_kasse.domain.errors import (
    BudgetExceededError,
    ConfirmationRequiredError,
    ValidationError,
)
from meine_kasse.domain.value_objects.money import format_euro


@dataclass(frozen=True, slots=True)
class BudgetPosition:
    """Stand einer Kostenstelle im Jahr, alle Werte in Cent."""

    annual_budget_cents: int
    movement_cents: int
    distributed_cents: int = 0

    @property
    def remaining_cents(self) -> int:
        """Haushaltsrest = wirksamer Jahresansatz - Ist-Bewegung (Soll - Haben)."""
        return self.annual_budget_cents - self.movement_cents


def is_checked(planning_enabled: bool, kind: CostCenterKind) -> bool:
    return planning_enabled and kind is CostCenterKind.STANDARD


def check_actual_booking(
    position: BudgetPosition,
    movement_delta_cents: int,
    *,
    planning_enabled: bool,
    kind: CostCenterKind,
) -> None:
    """Sperrt eine Ist-Buchung, die den Haushaltsrest unter 0 bringen würde.

    Entlastende Buchungen (Bewegung sinkt oder bleibt gleich) werden nie gesperrt.
    """
    if not is_checked(planning_enabled, kind) or movement_delta_cents <= 0:
        return
    rest_after = position.remaining_cents - movement_delta_cents
    if rest_after < 0:
        shortfall = -rest_after
        raise BudgetExceededError(
            f"Der Haushaltsrest reicht nicht aus: Es fehlen {format_euro(shortfall)}. "
            "Bitte zuerst Ansatz auf diese Kostenstelle umbuchen.",
            shortfall,
        )


def validate_budget_transfer_allowed(
    *,
    planning_enabled: bool,
    kinds: tuple[CostCenterKind, CostCenterKind],
    donor_is_leading: bool = True,
) -> None:
    """Ansatzumbuchung nur zwischen Kostenstellen mit Plan. Eine Einnahmenstelle darf nur
    abgeben (nie erhalten) und nur an eine Kostenstelle der Art `STANDARD`."""
    if not planning_enabled:
        raise ValidationError("Ansatzumbuchungen sind nur bei aktivierter Planung möglich.")
    allowed = (CostCenterKind.STANDARD, CostCenterKind.INCOME)
    if any(kind not in allowed for kind in kinds):
        raise ValidationError(
            "Ansatzumbuchungen sind nur zwischen Kostenstellen mit Planung möglich."
        )
    receiver = kinds[1] if donor_is_leading else kinds[0]
    if receiver is not CostCenterKind.STANDARD:
        raise ValidationError(
            "Eine Einnahmen-Kostenstelle kann nur Ansatz abgeben, nicht erhalten. "
            "Empfänger muss eine Kostenstelle mit Plan (Standard) sein."
        )


def check_budget_change(
    position: BudgetPosition,
    budget_delta_cents: int,
    *,
    negative_budget_confirmed: bool = False,
) -> None:
    """Prüft die Änderung des Jahresansatzes einer Kostenstelle.

    Ein sinkender Ansatz darf weder unter die Ist-Bewegung (Haushaltsrest nicht unter 0) noch
    unter den bereits auf Monate verteilten Ansatz fallen. Ist die Ist-Bewegung negativ (z. B.
    Zuführung von Außenmitteln ohne Ansatz) und nichts verteilt, darf der Haushaltsrest auch
    ohne Ansatz abgegeben werden. Der Ansatz wird dadurch negativ; das verlangt eine Bestätigung.
    """
    if budget_delta_cents >= 0:
        return
    budget_after = position.annual_budget_cents + budget_delta_cents
    if position.distributed_cents > 0:
        lowest_allowed = max(position.movement_cents, position.distributed_cents)
    else:
        lowest_allowed = position.movement_cents
    if budget_after < lowest_allowed:
        shortfall = lowest_allowed - budget_after
        available = max(0, position.annual_budget_cents - lowest_allowed)
        raise BudgetExceededError(
            f"Der abzugebende Ansatz ist zu hoch: Es können höchstens {format_euro(available)} "
            "umgebucht werden. Bei verteiltem Ansatz zuerst die Monatsplanung verringern.",
            shortfall,
        )
    if budget_after < 0 and not negative_budget_confirmed:
        raise ConfirmationRequiredError(
            "Die Kostenstelle hat nicht genug Ansatz, aber Haushaltsrest "
            f"({format_euro(position.remaining_cents)}), z. B. aus einer Zuführung. "
            f"Der Ansatz wird dadurch {format_euro(budget_after)} (negativ). "
            "Der Haushaltsrest wird an die andere Kostenstelle weitergegeben."
        )
