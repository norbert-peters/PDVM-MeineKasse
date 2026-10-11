"""Anfangssalden (Vorträge) der Konten (siehe Architekturvorgabe 2.10).

Ein Konto hat höchstens einen manuell erfassten Vortrag. Er ist nur editierbar, solange das
Konto kein Vorjahr hat und der Januar des Jahres nicht abgeschlossen ist. Spätere Jahre leiten
ihren Vortrag aus Vortrag und Buchungen ab.
"""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from meine_kasse.domain.entities import AccountOpeningBalance


class OpeningSource(StrEnum):
    MANUAL = "MANUAL"  # manuell zum 01.01. dieses Jahres erfasst
    CARRIED = "CARRIED"  # aus dem Vorjahr abgeleitet
    NONE = "NONE"  # kein Vortrag


class OpeningState(StrEnum):
    EDITABLE = "EDITABLE"
    CARRIED = "CARRIED"  # Vorjahr vorhanden, nicht editierbar
    LOCKED = "LOCKED"  # Januar (oder Jahr) abgeschlossen


@dataclass(frozen=True, slots=True)
class OpeningEditability:
    state: OpeningState
    message: str

    @property
    def editable(self) -> bool:
        return self.state is OpeningState.EDITABLE


def is_january_closed(
    year: int, closed_months: Collection[tuple[int, int]], closed_years: Collection[int]
) -> bool:
    return year in closed_years or (year, 1) in closed_months


def opening_editability(
    *,
    year: int,
    manual: AccountOpeningBalance | None,
    has_bookings_before_year: bool,
    closed_months: Collection[tuple[int, int]],
    closed_years: Collection[int],
) -> OpeningEditability:
    """Ob der Vortrag eines Kontos für ein Jahr editiert werden darf."""
    if is_january_closed(year, closed_months, closed_years):
        return OpeningEditability(OpeningState.LOCKED, f"gesperrt: Januar {year} ist abgeschlossen")
    has_prior = has_bookings_before_year or (manual is not None and manual.year < year)
    if has_prior:
        return OpeningEditability(
            OpeningState.CARRIED, "aus dem Vorjahr übernommen, nicht editierbar"
        )
    if manual is not None and manual.year != year:
        if is_january_closed(manual.year, closed_months, closed_years):
            return OpeningEditability(
                OpeningState.LOCKED,
                f"gesperrt: Der Vortrag für {manual.year} ist bereits abgeschlossen",
            )
        return OpeningEditability(
            OpeningState.EDITABLE,
            f"editierbar (verschiebt den Vortrag von {manual.year} auf {year})",
        )
    return OpeningEditability(OpeningState.EDITABLE, f"editierbar bis Abschluss Januar {year}")


def opening_for_year(
    *, year: int, manual: AccountOpeningBalance | None, movements_before_year_cents: int
) -> int:
    """Vortrag zum 01.01. eines Jahres = manueller Vortrag + Bewegung der Vorjahre."""
    base = manual.amount_cents if manual is not None and manual.year <= year else 0
    return base + movements_before_year_cents


def opening_source(
    *,
    year: int,
    manual: AccountOpeningBalance | None,
    has_bookings_before_year: bool,
) -> OpeningSource:
    if manual is not None and manual.year == year:
        return OpeningSource.MANUAL
    if has_bookings_before_year or (manual is not None and manual.year < year):
        return OpeningSource.CARRIED
    return OpeningSource.NONE
