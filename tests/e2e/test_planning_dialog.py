import os
from datetime import date

import pytest

from conftest import World

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from meine_kasse.application.services.booking_control_service import (  # noqa: E402
    BookingControlService,
)
from meine_kasse.application.services.booking_service import BookingService  # noqa: E402
from meine_kasse.application.services.planning_service import (  # noqa: E402
    MonthPlanInput,
    PlanningService,
)
from meine_kasse.domain.enums import BookingType, ObjectKind, PlanMode, Side  # noqa: E402
from meine_kasse.domain.services.booking_rules import Stelle  # noqa: E402
from meine_kasse.infrastructure.database.models import (  # noqa: E402
    PeriodClosureModel,
    YearClosureModel,
)
from meine_kasse.infrastructure.database.session import Database  # noqa: E402
from meine_kasse.presentation.dialogs.planning_dialog import PlanningDialog  # noqa: E402
from meine_kasse.presentation.dialogs.quarter_amounts_dialog import (  # noqa: E402
    QuarterAmountsDialog,
)

YEAR = 2026
PLAN, RESERVE, ACTUAL_DEBIT, ACTUAL_CREDIT, STATUS = 1, 3, 4, 5, 8


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


def _dialog(
    planning: PlanningService, control: BookingControlService, world: World
) -> PlanningDialog:
    return PlanningDialog(planning, control, world.actor)


def _set(dialog: PlanningDialog, row: int, column: int, text: str) -> None:
    item = dialog.table.item(row, column)
    assert item is not None
    item.setText(text)


def _text(dialog: PlanningDialog, row: int, column: int) -> str:
    item = dialog.table.item(row, column)
    assert item is not None
    return item.text()


def _editable(dialog: PlanningDialog, row: int, column: int) -> bool:
    item = dialog.table.item(row, column)
    assert item is not None
    return bool(item.flags() & Qt.ItemFlag.ItemIsEditable)


def _close_month(database: Database, world: World, month: int) -> None:
    with database.session_factory() as session:
        session.add(
            PeriodClosureModel(
                year=YEAR,
                month=month,
                closed_on=date(YEAR, month, 28),
                closed_by_user_id=world.actor,
                signature="x" * 64,
            )
        )
        session.commit()


def test_dialog_offers_only_planned_cost_centers_and_the_current_year(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    dialog = _dialog(planning, booking_control, world)

    assert dialog.cost_center_combo.count() == 2
    assert dialog.year_spin.value() == 2026
    assert dialog.table.rowCount() == 12
    assert _text(dialog, 0, 0) == "Januar"
    assert _text(dialog, 0, STATUS) == "offen (frei)"
    assert dialog.base_edit.isEnabled() is True


def test_saving_stores_the_plan(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    dialog = _dialog(planning, booking_control, world)
    dialog.base_edit.setText("1.200,00")
    dialog.base_edit.textEdited.emit("1.200,00")
    _set(dialog, 0, PLAN, "100,00")
    _set(dialog, 5, PLAN, "250,50")
    _set(dialog, 5, RESERVE, "40,00")
    dialog.mode_combos[6].setCurrentIndex(dialog.mode_combos[6].findData("IRREGULAR"))
    dialog.carry_in_edit.setText("15,00")
    dialog.save_button.click()

    assert "gespeichert" in dialog.message_label.text()
    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.base_budget_cents == 120000
    assert view.reserve_carry_in_cents == 1500
    assert view.months[0].plan_cents == 10000
    assert (view.months[5].plan_cents, view.months[5].reserve_plan_cents) == (25050, 4000)
    assert view.months[5].plan_mode is PlanMode.IRREGULAR
    assert _text(dialog, 5, PLAN) == "250,50 €"


def test_summary_updates_while_typing_and_warns_about_overdistribution(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    dialog = _dialog(planning, booking_control, world)
    dialog.base_edit.setText("100,00")
    dialog.base_edit.textEdited.emit("100,00")
    _set(dialog, 0, PLAN, "60,00")
    _set(dialog, 1, PLAN, "30,00")

    assert dialog.effective_label.text() == "100,00 €"
    assert dialog.distributed_label.text() == "90,00 €"
    assert dialog.undistributed_label.text() == "10,00 €"
    assert dialog.remaining_label.text() == "100,00 €"

    _set(dialog, 2, PLAN, "20,00")
    assert dialog.undistributed_label.text() == "-10,00 €"
    assert "übersteigt" in dialog.message_label.text()

    dialog.save_button.click()
    assert "übersteigt" in dialog.message_label.text()
    assert planning.get_plan_view(world.cc_a, YEAR).distributed_cents == 0


def test_invalid_amount_is_reported_without_crashing(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    dialog = _dialog(planning, booking_control, world)
    _set(dialog, 3, PLAN, "abc")
    assert "April" in dialog.message_label.text()
    dialog.save_button.click()
    assert "April" in dialog.message_label.text()
    assert planning.get_plan_view(world.cc_a, YEAR).base_budget_cents == 0


def test_even_distribution_fills_all_open_months(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    dialog = _dialog(planning, booking_control, world)
    dialog.base_edit.setText("1.200,00")
    dialog.base_edit.textEdited.emit("1.200,00")
    dialog.distribute_button.click()

    assert {_text(dialog, row, PLAN) for row in range(12)} == {"100,00 €"}
    assert dialog.undistributed_label.text() == "0,00 €"


def test_even_distribution_skips_closed_months(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=120000,
        months=[MonthPlanInput(1, 30000)],
        actor_id=world.actor,
    )
    _close_month(database, world, 1)
    dialog = _dialog(planning, booking_control, world)

    assert _text(dialog, 0, STATUS) == "abgeschlossen (fix)"
    assert not _editable(dialog, 0, PLAN)
    assert dialog.mode_combos[1].isEnabled() is False
    assert _editable(dialog, 1, PLAN)

    dialog.distribute_button.click()
    assert _text(dialog, 0, PLAN) == "300,00 €"
    assert _text(dialog, 1, PLAN) == "81,82 €"
    dialog.save_button.click()
    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.distributed_cents == 120000


def test_quarter_amounts_are_split_over_the_months_of_the_quarter(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_exec(self: QuarterAmountsDialog) -> int:
        self.amounts = {1: 3000, 2: 0, 3: 600, 4: 0}
        return 1

    monkeypatch.setattr(QuarterAmountsDialog, "exec", fake_exec)
    dialog = _dialog(planning, booking_control, world)
    dialog.base_edit.setText("100,00")
    dialog.base_edit.textEdited.emit("100,00")
    dialog.quarter_button.click()

    assert [_text(dialog, row, PLAN) for row in (0, 1, 2)] == ["10,00 €"] * 3
    assert [_text(dialog, row, PLAN) for row in (6, 7, 8)] == ["2,00 €"] * 3
    assert dialog.mode_combos[1].currentData() == PlanMode.QUARTERLY.value
    assert dialog.mode_combos[4].currentData() == PlanMode.MONTHLY.value


def test_quarter_dialog_parses_amounts(qapp: QApplication) -> None:
    dialog = QuarterAmountsDialog()
    dialog.edits[1].setText("300,00")
    dialog.edits[3].setText("1.000,50")
    dialog.save()
    assert dialog.amounts == {1: 30000, 2: 0, 3: 100050, 4: 0}


def test_base_is_locked_when_planning_is_active(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    booking_control.update(planning_enabled=True, current_year=YEAR, current_month=5)
    dialog = _dialog(planning, booking_control, world)

    assert dialog.base_edit.isEnabled() is False
    assert "Ansatzumbuchung" in dialog.base_hint.text()
    assert dialog.save_button.isEnabled() is True


def test_year_closed_makes_everything_read_only(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    with database.session_factory() as session:
        session.add(
            YearClosureModel(
                year=YEAR,
                closed_on=date(YEAR, 12, 31),
                closed_by_user_id=world.actor,
                signature="x" * 64,
            )
        )
        session.commit()
    dialog = _dialog(planning, booking_control, world)

    assert dialog.save_button.isEnabled() is False
    assert dialog.base_edit.isEnabled() is False
    assert not _editable(dialog, 0, PLAN)
    assert "abgeschlossen" in dialog.base_hint.text()


def test_dialog_shows_actuals_and_deviation(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=100000,
        months=[MonthPlanInput(5, 20000)],
        actor_id=world.actor,
    )
    for side, cents in ((Side.DEBIT, 15000), (Side.CREDIT, 2500)):
        bookings.post(
            booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
            entry_side=side,
            amount_cents=cents,
            booking_date=date(2026, 5, 10),
            origin_date=date(2026, 5, 10),
            leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
            second=Stelle(ObjectKind.ACCOUNT, world.giro),
            actor_id=world.actor,
        )
    dialog = _dialog(planning, booking_control, world)

    assert _text(dialog, 4, ACTUAL_DEBIT) == "150,00 €"
    assert _text(dialog, 4, ACTUAL_CREDIT) == "25,00 €"
    assert _text(dialog, 4, 6) == "125,00 €"
    assert _text(dialog, 4, 7) == "75,00 €"
    assert dialog.movement_label.text() == "125,00 €"
    assert dialog.remaining_label.text() == "875,00 €"


def test_switching_with_unsaved_changes_asks_and_can_keep_the_selection(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = _dialog(planning, booking_control, world)
    _set(dialog, 0, PLAN, "10,00")
    first = dialog.cost_center_combo.currentData()

    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)
    dialog.cost_center_combo.setCurrentIndex(1)
    assert dialog.cost_center_combo.currentData() == first
    assert _text(dialog, 0, PLAN) == "10,00"

    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    dialog.cost_center_combo.setCurrentIndex(1)
    assert dialog.cost_center_combo.currentData() == world.cc_b
    assert _text(dialog, 0, PLAN) == "0,00 €"


def test_reset_discards_changes(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    dialog = _dialog(planning, booking_control, world)
    _set(dialog, 0, PLAN, "10,00")
    dialog.reset_button.click()
    assert _text(dialog, 0, PLAN) == "0,00 €"
