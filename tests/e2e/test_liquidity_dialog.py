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

    first = dialog.table.item(0, 7)
    assert first is not None and first.text() == "-100,00 €"
    bank = dialog.table.item(0, 1)
    assert bank is not None and bank.text() == "100,00 €"
    movement = dialog.table.item(0, 2)
    assert movement is not None and movement.text() == "0,00 €"
    status = dialog.table.item(0, 9)
    assert status is not None and status.text() == "Fehlbetrag"
    assert "Januar" in dialog.message_label.text()
    assert dialog.table.rowCount() == 12


def test_dialog_without_plan_reports_coverage(
    qapp: QApplication, planning: PlanningService, booking_control: BookingControlService
) -> None:
    dialog = LiquidityDialog(planning, booking_control)

    assert "decken den Bedarf in jedem Monat" in dialog.message_label.text()


def test_pdf_table_contains_every_month_and_the_totals(
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

    table = dialog.pdf_table()

    assert table is not None
    assert table.title == "Liquiditätsplanung 2026"
    assert len(table.rows) == 12
    assert table.rows[0].cells[0] == "Januar"
    assert table.rows[0].cells[7] == "-100,00 €"
    assert table.rows[0].cells[9] == "Fehlbetrag"
    assert table.total_row is not None
    assert table.total_row.cells[:1] == ("Gesamt",)
    assert table.total_row.cells[6:8] == ("1.200,00 €", "-1.200,00 €")
    assert len(table.columns) == len(table.rows[0].cells)
    assert not dialog.pdf_button.isVisibleTo(dialog)
