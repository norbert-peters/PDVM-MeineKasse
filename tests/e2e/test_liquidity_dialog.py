import os

import pytest

from conftest import World

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from meine_kasse.application.services.booking_control_service import (  # noqa: E402
    BookingControlService,
)
from meine_kasse.application.services.planning_service import (  # noqa: E402
    MonthPlanInput,
    PlanningService,
)
from meine_kasse.presentation.dialogs.liquidity_dialog import LiquidityDialog  # noqa: E402

YEAR = 2026


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


def test_dialog_shows_the_months_with_a_shortfall(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=120000,
        months=[MonthPlanInput(month, 10000) for month in range(1, 13)],
        actor_id=world.actor,
    )
    dialog = LiquidityDialog(planning, booking_control)
    dialog.year_spin.setValue(YEAR)

    first = dialog.table.item(0, 5)
    assert first is not None and first.text() == "-100,00 €"
    status = dialog.table.item(0, 7)
    assert status is not None and status.text() == "Fehlbetrag"
    assert "Januar" in dialog.message_label.text()
    assert dialog.table.rowCount() == 12


def test_dialog_without_plan_reports_coverage(
    qapp: QApplication, planning: PlanningService, booking_control: BookingControlService
) -> None:
    dialog = LiquidityDialog(planning, booking_control)

    assert "decken den Bedarf in jedem Monat" in dialog.message_label.text()
