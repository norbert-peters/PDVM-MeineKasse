from datetime import date

import pytest

from meine_kasse.domain.errors import PeriodError
from meine_kasse.domain.services.period_rules import bookable_window, ensure_bookable


def test_window_is_previous_current_and_next_month() -> None:
    assert bookable_window(2026, 5) == (date(2026, 4, 1), date(2026, 6, 30))


def test_window_wraps_across_year_boundaries() -> None:
    assert bookable_window(2026, 1) == (date(2025, 12, 1), date(2026, 2, 28))
    assert bookable_window(2026, 12) == (date(2026, 11, 1), date(2027, 1, 31))


@pytest.mark.parametrize("booking_date", [date(2026, 4, 1), date(2026, 5, 15), date(2026, 6, 30)])
def test_dates_inside_window_are_bookable(booking_date: date) -> None:
    ensure_bookable(booking_date, current_year=2026, current_month=5)


@pytest.mark.parametrize("booking_date", [date(2026, 3, 31), date(2026, 7, 1)])
def test_dates_outside_window_are_rejected(booking_date: date) -> None:
    with pytest.raises(PeriodError, match="außerhalb"):
        ensure_bookable(booking_date, current_year=2026, current_month=5)


def test_closed_month_is_rejected() -> None:
    with pytest.raises(PeriodError, match="04/2026"):
        ensure_bookable(
            date(2026, 4, 10), current_year=2026, current_month=5, closed_months={(2026, 4)}
        )


def test_closed_year_is_rejected() -> None:
    with pytest.raises(PeriodError, match="2026"):
        ensure_bookable(date(2026, 5, 10), current_year=2026, current_month=5, closed_years={2026})
