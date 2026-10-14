import pytest

from meine_kasse.domain.errors import PlanPeriodError
from meine_kasse.domain.services.period_rules import ensure_plan_year_usable


def _check(
    plan_year: int,
    *,
    current_year: int = 2026,
    closed: tuple[int, ...] = (),
    planning_checked: bool = True,
    plan_exists: bool = True,
) -> None:
    ensure_plan_year_usable(
        cost_center_label="100 Lebensmittel",
        plan_year=plan_year,
        current_year=current_year,
        closed_years=closed,
        planning_checked=planning_checked,
        plan_exists=plan_exists,
    )


def test_current_year_is_usable_without_an_existing_plan() -> None:
    _check(2026, plan_exists=False)


def test_other_year_needs_a_plan_only_when_planning_is_checked() -> None:
    _check(2025, plan_exists=True)
    _check(2025, plan_exists=False, planning_checked=False)
    with pytest.raises(PlanPeriodError, match="100 Lebensmittel.*2025.*kein Plan"):
        _check(2025, plan_exists=False)


@pytest.mark.parametrize("planning_checked", [True, False])
def test_closed_year_is_never_usable(planning_checked: bool) -> None:
    with pytest.raises(PlanPeriodError, match="2025.*abgeschlossen"):
        _check(2025, closed=(2025,), planning_checked=planning_checked)
    with pytest.raises(PlanPeriodError, match="abgeschlossen"):
        _check(2026, closed=(2026,), planning_checked=planning_checked)
