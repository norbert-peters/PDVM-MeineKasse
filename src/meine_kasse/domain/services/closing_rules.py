"""Monats- und Jahresabschluss: Signatur und Konsistenzprüfung (Architekturvorgabe 5.3, 6.4).

Die Signatur ist ein SHA-256-Hash über einen kanonisch serialisierten Datenbestand. Sie macht
nachträgliche Änderungen erkennbar. Sie ersetzt keine revisionssichere Archivierung.
"""

import hashlib
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from meine_kasse.domain.entities import Booking, MonthlyPlan
from meine_kasse.domain.enums import ClosureKind
from meine_kasse.domain.errors import ValidationError

MONTHS_PER_YEAR = 12
MIN_REASON_LENGTH = 10


@dataclass(frozen=True, slots=True)
class ClosureRef:
    """Verweis auf einen Abschluss (Monat oder Jahr)."""

    kind: ClosureKind
    year: int
    month: int | None = None

    @property
    def label(self) -> str:
        if self.kind is ClosureKind.YEAR:
            return f"Jahr {self.year}"
        assert self.month is not None
        return f"Monat {self.month:02d}/{self.year}"

    @property
    def order_key(self) -> tuple[int, int]:
        """Reihenfolge der Abschlüsse: Der Jahresabschluss steht hinter dem Dezember seines
        Jahres und vor dem Januar des Folgejahres."""
        if self.kind is ClosureKind.YEAR:
            return (self.year, MONTHS_PER_YEAR + 1)
        assert self.month is not None
        return (self.year, self.month)


def latest_closure(
    months: Collection[tuple[int, int]], years: Collection[int]
) -> ClosureRef | None:
    """Der zuletzt liegende Abschluss. Nur dieser darf wiedereröffnet werden."""
    refs = [ClosureRef(ClosureKind.MONTH, year, month) for year, month in months]
    refs += [ClosureRef(ClosureKind.YEAR, year) for year in years]
    return max(refs, key=lambda ref: ref.order_key, default=None)


def validate_reopen_reason(reason: str) -> str:
    """Eine Begründung ist Pflicht, damit das Wiedereröffnen nachvollziehbar bleibt."""
    cleaned = reason.strip()
    if len(cleaned) < MIN_REASON_LENGTH:
        raise ValidationError(
            f"Bitte eine Begründung mit mindestens {MIN_REASON_LENGTH} Zeichen angeben."
        )
    return cleaned


def next_period(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _booking_record(booking: Booking) -> dict[str, Any]:
    return {
        "id": booking.id,
        "booking_date": booking.booking_date.isoformat(),
        "origin_date": booking.origin_date.isoformat(),
        "booking_type": booking.booking_type.value,
        "entry_side": booking.entry_side.value,
        "amount_cents": booking.amount_cents,
        "merchant": booking.merchant,
        "booking_text": booking.booking_text,
        "reversal_of_id": booking.reversal_of_id,
        "legs": [
            {
                "position": leg.position,
                "side": leg.side.value,
                "cost_center_id": leg.cost_center_id,
                "account_id": leg.account_id,
            }
            for leg in sorted(booking.legs, key=lambda item: item.position)
        ],
    }


def _digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def month_signature(
    year: int,
    month: int,
    bookings: Sequence[Booking],
    plans: Sequence[tuple[str, MonthlyPlan]],
) -> str:
    """Signatur über alle Buchungen (inklusive Ansatzumbuchungen) und Monatsplanwerte eines Monats.

    Die Reihenfolge der Eingabe spielt keine Rolle.
    """
    return _digest(
        {
            "kind": "month",
            "year": year,
            "month": month,
            "bookings": sorted((_booking_record(b) for b in bookings), key=lambda r: r["id"]),
            "plans": sorted(
                (
                    {
                        "cost_center_id": cost_center_id,
                        "plan_cents": plan.plan_cents,
                        "reserve_plan_cents": plan.reserve_plan_cents,
                        "plan_mode": plan.plan_mode.value,
                    }
                    for cost_center_id, plan in plans
                    if plan.month == month
                ),
                key=lambda r: r["cost_center_id"],
            ),
        }
    )


def year_signature(year: int, month_signatures: Mapping[int, str]) -> str:
    """Signatur über die zwölf Monatssignaturen eines Jahres."""
    if sorted(month_signatures) != list(range(1, MONTHS_PER_YEAR + 1)):
        raise ValidationError("Für die Jahressignatur werden alle zwölf Monatssignaturen benötigt.")
    return _digest(
        {
            "kind": "year",
            "year": year,
            "months": [month_signatures[month] for month in range(1, MONTHS_PER_YEAR + 1)],
        }
    )


def projection_mismatches(
    booked: Mapping[str, tuple[int, int]], projected: Mapping[str, tuple[int, int]]
) -> list[str]:
    """Kostenstellen, deren fortgeschriebene Soll-/Haben-Summen nicht den Buchungen entsprechen."""
    mismatched = []
    for cost_center_id in sorted(set(booked) | set(projected)):
        if booked.get(cost_center_id, (0, 0)) != projected.get(cost_center_id, (0, 0)):
            mismatched.append(cost_center_id)
    return mismatched
