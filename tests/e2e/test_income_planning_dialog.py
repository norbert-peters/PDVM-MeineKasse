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
from meine_kasse.application.services.master_data_service import MasterDataService  # noqa: E402
from meine_kasse.application.services.planning_service import PlanningService  # noqa: E402
from meine_kasse.domain.enums import (  # noqa: E402
    BookingType,
    CostCenterKind,
    IncomeMode,
    ObjectKind,
    Side,
)
from meine_kasse.domain.services.booking_rules import Stelle  # noqa: E402
from meine_kasse.infrastructure.database.models import PeriodClosureModel  # noqa: E402
from meine_kasse.infrastructure.database.session import Database  # noqa: E402
from meine_kasse.presentation.dialogs.income_planning_dialog import (  # noqa: E402
    IncomePlanningDialog,
)

YEAR = 2026
PLAN, DEBIT, CREDIT, REALIZED, DEVIATION, STATUS = 1, 2, 3, 4, 5, 6


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


@pytest.fixture
def rente(master_data: MasterDataService, world: World) -> str:
    return master_data.create_cost_center(
        number="900",
        name="Rente",
        valid_from=date(2026, 1, 1),
        kind=CostCenterKind.INCOME,
        income_mode=IncomeMode.PLAN,
    )


def _set(dialog: IncomePlanningDialog, row: int, column: int, text: str) -> None:
    item = dialog.table.item(row, column)
    assert item is not None
    item.setText(text)


def _text(dialog: IncomePlanningDialog, row: int, column: int) -> str:
    item = dialog.table.item(row, column)
    assert item is not None
    return item.text()


def _editable(dialog: IncomePlanningDialog, row: int, column: int) -> bool:
    item = dialog.table.item(row, column)
    assert item is not None
    return bool(item.flags() & Qt.ItemFlag.ItemIsEditable)


def _dialog(
    planning: PlanningService, control: BookingControlService, world: World
) -> IncomePlanningDialog:
    return IncomePlanningDialog(planning, control, world.actor)


def test_dialog_offers_only_income_cost_centers(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
    rente: str,
) -> None:
    dialog = _dialog(planning, booking_control, world)

    assert dialog.cost_center_combo.count() == 1
    assert dialog.cost_center_combo.currentData() == rente
    assert dialog.year_spin.value() == 2026
    assert dialog.table.rowCount() == 12
    assert _text(dialog, 0, 0) == "Januar"
    assert _text(dialog, 0, STATUS) == "offen (frei)"
    assert dialog.mode_label.text().startswith("Nach Plan")
    assert _editable(dialog, 0, PLAN) is True
    assert _editable(dialog, 0, REALIZED) is False


def test_dialog_without_income_cost_center_is_disabled(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    dialog = _dialog(planning, booking_control, world)

    assert dialog.cost_center_combo.count() == 0
    assert dialog.save_button.isEnabled() is False
    assert "keine aktive Einnahmen-Kostenstelle" in dialog.message_label.text()


def test_dialog_distributes_and_saves_the_expected_income(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
    rente: str,
) -> None:
    dialog = _dialog(planning, booking_control, world)
    dialog.total_edit.setText("12.000,00")
    dialog.distribute_button.click()

    assert _text(dialog, 0, PLAN) == "1.000,00 €"
    assert dialog.planned_label.text() == "12.000,00 €"
    assert dialog.free_label.text() == "12.000,00 €"
    dialog.save_button.click()

    assert "gespeichert" in dialog.message_label.text()
    assert planning.get_income_view(rente, YEAR).planned_cents == 1200000


def test_dialog_shows_plan_versus_booked_income(
    qapp: QApplication,
    planning: PlanningService,
    bookings: BookingService,
    booking_control: BookingControlService,
    world: World,
    rente: str,
) -> None:
    bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=Side.CREDIT,
        amount_cents=90000,
        booking_date=date(2026, 5, 10),
        origin_date=date(2026, 5, 10),
        leading=Stelle(ObjectKind.COST_CENTER, rente),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        actor_id=world.actor,
    )
    dialog = _dialog(planning, booking_control, world)
    _set(dialog, 4, PLAN, "1.000,00")

    assert _text(dialog, 4, CREDIT) == "900,00 €"
    assert _text(dialog, 4, REALIZED) == "900,00 €"
    assert _text(dialog, 4, DEVIATION) == "-100,00 €"
    assert dialog.realized_label.text() == "900,00 €"
    assert dialog.expected_label.text() == "100,00 €"


def test_dialog_blocks_closed_months_and_discards_on_reset(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
    rente: str,
) -> None:
    with database.session_factory() as session:
        session.add(
            PeriodClosureModel(
                year=YEAR,
                month=1,
                closed_on=date(YEAR, 1, 31),
                closed_by_user_id=world.actor,
                signature="x" * 64,
            )
        )
        session.commit()
    dialog = _dialog(planning, booking_control, world)

    assert _text(dialog, 0, STATUS) == "abgeschlossen (fix)"
    assert _editable(dialog, 0, PLAN) is False
    _set(dialog, 1, PLAN, "50,00")
    assert dialog.planned_label.text() == "50,00 €"
    dialog.reset_button.click()
    assert _text(dialog, 1, PLAN) == "0,00 €"


def test_dialog_reports_invalid_amounts_and_asks_before_discarding(
    qapp: QApplication,
    planning: PlanningService,
    booking_control: BookingControlService,
    world: World,
    rente: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = _dialog(planning, booking_control, world)
    _set(dialog, 0, PLAN, "abc")
    assert "Januar" in dialog.message_label.text()

    dialog.save_button.click()
    assert "Januar" in dialog.message_label.text()

    _set(dialog, 0, PLAN, "10,00")
    asked: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, title, _text: asked.append(title) or QMessageBox.StandardButton.No,
    )
    dialog.year_spin.setValue(2027)
    assert asked == ["Ungespeicherte Änderungen"]
    assert dialog.year_spin.value() == 2026
