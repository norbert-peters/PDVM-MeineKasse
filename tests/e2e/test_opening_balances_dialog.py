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
from meine_kasse.application.services.closing_service import ClosingService  # noqa: E402
from meine_kasse.application.services.opening_balance_service import (  # noqa: E402
    OpeningBalanceService,
)
from meine_kasse.domain.enums import BookingType, ObjectKind, Side  # noqa: E402
from meine_kasse.domain.services.booking_rules import Stelle  # noqa: E402
from meine_kasse.presentation.dialogs.opening_balances_dialog import (  # noqa: E402
    OpeningBalancesDialog,
)

OPENING, SOURCE, MOVEMENT, BALANCE, STATUS = 1, 2, 3, 4, 5


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


def _dialog(
    openings: OpeningBalanceService, control: BookingControlService, world: World
) -> OpeningBalancesDialog:
    return OpeningBalancesDialog(openings, control, world.actor)


def _row_of(dialog: OpeningBalancesDialog, label: str) -> int:
    for row in range(dialog.table.rowCount()):
        item = dialog.table.item(row, 0)
        if item is not None and item.text().startswith(label):
            return row
    raise AssertionError(label)


def _cell(dialog: OpeningBalancesDialog, row: int, column: int) -> str:
    item = dialog.table.item(row, column)
    assert item is not None
    return item.text()


def _editable(dialog: OpeningBalancesDialog, row: int, column: int = OPENING) -> bool:
    item = dialog.table.item(row, column)
    assert item is not None
    return bool(item.flags() & Qt.ItemFlag.ItemIsEditable)


def _set(dialog: OpeningBalancesDialog, row: int, text: str) -> None:
    item = dialog.table.item(row, OPENING)
    assert item is not None
    item.setText(text)


def _spend(bookings: BookingService, world: World, day: date, cents: int = 5000) -> None:
    bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=Side.DEBIT,
        amount_cents=cents,
        booking_date=day,
        origin_date=day,
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        actor_id=world.actor,
    )


def test_dialog_lists_accounts_with_editable_openings(
    qapp: QApplication,
    openings: OpeningBalanceService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    dialog = _dialog(openings, booking_control, world)

    assert dialog.year_spin.value() == 2026
    assert dialog.table.rowCount() == 2
    assert dialog.table.horizontalHeaderItem(OPENING).text() == "Anfangssaldo 01.01.2026"  # type: ignore[union-attr]
    giro = _row_of(dialog, "1000")
    assert _editable(dialog, giro) and not _editable(dialog, giro, SOURCE)
    assert _cell(dialog, giro, OPENING) == ""
    assert _cell(dialog, giro, SOURCE) == "kein Vortrag"
    assert "editierbar bis Abschluss Januar 2026" in _cell(dialog, giro, STATUS)


def test_saving_stores_openings_and_shows_the_balance(
    qapp: QApplication,
    openings: OpeningBalanceService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    _spend(bookings, world, date(2026, 5, 10), 5000)
    dialog = _dialog(openings, booking_control, world)
    giro = _row_of(dialog, "1000")
    _set(dialog, giro, "1.000,00")
    _set(dialog, _row_of(dialog, "2000"), "-25,50")
    assert dialog.has_changes() is True
    dialog.save_button.click()

    assert "2 Anfangssaldo" in dialog.message_label.text()
    assert dialog.has_changes() is False
    assert _cell(dialog, giro, OPENING) == "1.000,00 €"
    assert _cell(dialog, giro, SOURCE) == "manuell erfasst"
    assert _cell(dialog, giro, MOVEMENT) == "-50,00 €"
    assert _cell(dialog, giro, BALANCE) == "950,00 €"
    assert bookings.account_balance(world.giro) == 95000
    assert bookings.account_balance(world.savings) == -2550


def test_clearing_the_field_removes_the_opening(
    qapp: QApplication,
    openings: OpeningBalanceService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    openings.set_opening_balance(world.giro, 2026, 1000, actor_id=world.actor)
    dialog = _dialog(openings, booking_control, world)
    giro = _row_of(dialog, "1000")
    assert _cell(dialog, giro, OPENING) == "10,00 €"

    _set(dialog, giro, "")
    dialog.save_button.click()

    assert bookings.account_balance(world.giro) == 0
    assert _cell(dialog, giro, SOURCE) == "kein Vortrag"


def test_invalid_input_is_reported_and_valid_rows_are_still_saved(
    qapp: QApplication,
    openings: OpeningBalanceService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    dialog = _dialog(openings, booking_control, world)
    _set(dialog, _row_of(dialog, "1000"), "abc")
    _set(dialog, _row_of(dialog, "2000"), "5,00")
    dialog.save_button.click()

    assert "1000 Girokonto" in dialog.message_label.text()
    assert "ungültig" in dialog.message_label.text()
    assert bookings.account_balance(world.savings) == 500
    assert bookings.account_balance(world.giro) == 0


def test_following_year_shows_derived_openings_read_only(
    qapp: QApplication,
    openings: OpeningBalanceService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)
    _spend(bookings, world, date(2026, 5, 10), 5000)
    dialog = _dialog(openings, booking_control, world)
    dialog.year_spin.setValue(2027)

    giro = _row_of(dialog, "1000")
    assert _cell(dialog, giro, OPENING) == "950,00 €"
    assert _cell(dialog, giro, SOURCE) == "aus Vorjahr übernommen"
    assert not _editable(dialog, giro)
    assert "nicht editierbar" in _cell(dialog, giro, STATUS)
    assert _editable(dialog, _row_of(dialog, "2000"))


def test_closed_january_locks_the_openings_in_the_dialog(
    qapp: QApplication,
    openings: OpeningBalanceService,
    booking_control: BookingControlService,
    closing: ClosingService,
    world: World,
) -> None:
    booking_control.update(planning_enabled=False, current_year=2026, current_month=1)
    openings.set_opening_balance(world.giro, 2026, 100000, actor_id=world.actor)
    closing.close_month(actor_id=world.actor)

    dialog = _dialog(openings, booking_control, world)
    dialog.year_spin.setValue(2026)

    giro = _row_of(dialog, "1000")
    assert not _editable(dialog, giro)
    assert "Januar 2026 ist abgeschlossen" in _cell(dialog, giro, STATUS)
    assert _cell(dialog, giro, OPENING) == "1.000,00 €"
    assert dialog.has_changes() is False


def test_switching_the_year_asks_before_discarding_changes(
    qapp: QApplication,
    openings: OpeningBalanceService,
    booking_control: BookingControlService,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = _dialog(openings, booking_control, world)
    _set(dialog, _row_of(dialog, "1000"), "10,00")

    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)
    dialog.year_spin.setValue(2027)
    assert dialog.year_spin.value() == 2026
    assert _cell(dialog, _row_of(dialog, "1000"), OPENING) == "10,00"

    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    dialog.year_spin.setValue(2027)
    assert dialog.year_spin.value() == 2027
    assert _cell(dialog, _row_of(dialog, "1000"), OPENING) == ""
