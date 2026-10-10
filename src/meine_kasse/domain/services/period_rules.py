"""Buchungszeitraum und Abschlüsse (siehe Architekturvorgabe 2.5)."""

from collections.abc import Collection
from datetime import date, timedelta

from meine_kasse.domain.errors import PeriodError


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + offset
    return index // 12, index % 12 + 1


def bookable_window(current_year: int, current_month: int) -> tuple[date, date]:
    """Erster und letzter buchbarer Tag: aktueller Buchungsmonat, ein Monat davor und danach."""
    start_year, start_month = _shift_month(current_year, current_month, -1)
    after_year, after_month = _shift_month(current_year, current_month, 2)
    return date(start_year, start_month, 1), date(after_year, after_month, 1) - timedelta(days=1)


def ensure_bookable(
    booking_date: date,
    *,
    current_year: int,
    current_month: int,
    closed_months: Collection[tuple[int, int]] = (),
    closed_years: Collection[int] = (),
) -> None:
    if booking_date.year in closed_years:
        raise PeriodError(f"Das Jahr {booking_date.year} ist abgeschlossen.")
    if (booking_date.year, booking_date.month) in closed_months:
        raise PeriodError(
            f"Der Monat {booking_date.month:02d}/{booking_date.year} ist abgeschlossen."
        )
    first, last = bookable_window(current_year, current_month)
    if not first <= booking_date <= last:
        raise PeriodError(
            "Das Buchungsdatum liegt außerhalb des buchbaren Zeitraums "
            f"({first.strftime('%d.%m.%Y')} bis {last.strftime('%d.%m.%Y')})."
        )
