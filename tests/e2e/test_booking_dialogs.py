import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox  # noqa: E402

from meine_kasse.application.services.auth_service import AuthService  # noqa: E402
from meine_kasse.application.services.booking_control_service import (  # noqa: E402
    BookingControlService,
)
from meine_kasse.application.services.booking_service import BookingService  # noqa: E402
from meine_kasse.application.services.master_data_service import MasterDataService  # noqa: E402
from meine_kasse.application.services.planning_service import PlanningService  # noqa: E402
from meine_kasse.domain.enums import AccountType, BookingType, Side  # noqa: E402
from meine_kasse.infrastructure.database.models import (  # noqa: E402
    CostCenterPlanModel,
    PeriodClosureModel,
)
from meine_kasse.infrastructure.database.session import Database  # noqa: E402
from meine_kasse.presentation.dialogs.booking_control_dialog import (  # noqa: E402
    BookingControlDialog,
)
from meine_kasse.presentation.dialogs.booking_dialog import BookingDialog  # noqa: E402
from meine_kasse.presentation.dialogs.booking_list_dialog import BookingListDialog  # noqa: E402
from meine_kasse.presentation.dialogs.transfer_dialog import TransferDialog  # noqa: E402
from meine_kasse.presentation.labels import TRANSFER_LABEL  # noqa: E402


@dataclass(frozen=True)
class UiWorld:
    actor: str
    cc_a: str
    cc_b: str
    giro: str
    savings: str


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


@pytest.fixture
def ui_world(auth: AuthService, master_data: MasterDataService) -> UiWorld:
    actor = auth.create_user(
        name="admin", last_name="A", first_name="A", initial_password="Erstpasswort-1"
    )
    start = date(2026, 1, 1)
    return UiWorld(
        actor=actor,
        cc_a=master_data.create_cost_center(number="100", name="Lebensmittel", valid_from=start),
        cc_b=master_data.create_cost_center(number="200", name="Reisen", valid_from=start),
        giro=master_data.create_account(
            number="1000", name="Girokonto", account_type=AccountType.CHECKING
        ),
        savings=master_data.create_account(
            number="2000", name="Sparkonto", account_type=AccountType.SAVINGS
        ),
    )


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, text: messages.append(text) or None
    )
    yield messages


@pytest.fixture
def confirm_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes
    )


def _dialog(
    bookings: BookingService,
    master_data: MasterDataService,
    world: UiWorld,
    booking_id: str | None = None,
    preset: BookingType | None = None,
) -> BookingDialog:
    return BookingDialog(bookings, master_data, world.actor, booking_id, preset_type=preset)


def _choose(dialog: BookingDialog, leading: str, second: str) -> None:
    dialog.leading_combo.setCurrentIndex(dialog.leading_combo.findData(leading))
    dialog.second_combo.setCurrentIndex(dialog.second_combo.findData(second))


def _save(dialog: BookingDialog | TransferDialog) -> None:
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()


def _set_budget(database: Database, cost_center_id: str, cents: int) -> None:
    with database.session_factory() as session:
        session.add(
            CostCenterPlanModel(cost_center_id=cost_center_id, year=2026, base_budget_cents=cents)
        )
        session.commit()


# Buchungsdialog


def test_amount_fields_lock_each_other(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    dialog = _dialog(bookings, master_data, ui_world)
    assert dialog.soll_edit.isEnabled() and dialog.haben_edit.isEnabled()

    dialog.soll_edit.setText("0,00")
    assert dialog.haben_edit.isEnabled(), "bei Betrag 0 sind beide Felder bedienbar"

    dialog.soll_edit.setText("-5,50")
    assert dialog.haben_edit.isEnabled() is False
    assert dialog.soll_edit.isEnabled() is True

    dialog.soll_edit.clear()
    dialog.haben_edit.setText("12,00")
    assert dialog.soll_edit.isEnabled() is False

    dialog.haben_edit.setText("")
    assert dialog.soll_edit.isEnabled() and dialog.haben_edit.isEnabled()


def test_dialog_posts_debit_booking(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    dialog = _dialog(bookings, master_data, ui_world)
    _choose(dialog, ui_world.cc_a, ui_world.giro)
    dialog.soll_edit.setText("12,50")
    dialog.merchant_edit.setText("Markt")
    dialog.text_edit.setPlainText("Wocheneinkauf")
    _save(dialog)

    (view,) = bookings.list_bookings(year=2026)
    assert (view.amount_cents, view.entry_side) == (1250, Side.DEBIT)
    assert (view.merchant, view.booking_text) == ("Markt", "Wocheneinkauf")
    assert view.leading_label == "100 Lebensmittel"
    assert bookings.account_balance(ui_world.giro) == -1250


def test_dialog_keeps_negative_credit_amount_on_the_credit_side(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    dialog = _dialog(bookings, master_data, ui_world)
    _choose(dialog, ui_world.cc_a, ui_world.giro)
    dialog.haben_edit.setText("-3,00")
    _save(dialog)

    (view,) = bookings.list_bookings(year=2026)
    assert (view.amount_cents, view.entry_side) == (-300, Side.CREDIT)


def test_dialog_requires_an_amount_and_reports_invalid_input(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    dialog = _dialog(bookings, master_data, ui_world)
    _save(dialog)
    assert "ungleich 0" in dialog.error_label.text()

    dialog.soll_edit.setText("abc")
    _save(dialog)
    assert "ungültig" in dialog.error_label.text()
    assert bookings.list_bookings(year=2026) == []


def test_changing_the_booking_type_switches_labels_and_stellen(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    dialog = _dialog(bookings, master_data, ui_world)
    assert dialog.leading_label.text() == "Kostenstelle:"
    assert dialog.second_label.text() == "Konto:"
    assert dialog.leading_combo.count() == 2 and dialog.second_combo.count() == 2

    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData("BUDGET_TRANSFER"))
    assert dialog.leading_label.text() == "Kostenstelle (führend):"
    assert dialog.leading_combo.findData(ui_world.cc_a) >= 0
    assert dialog.leading_combo.findData(ui_world.giro) < 0
    assert dialog.type_combo.findData("ACCOUNT_TO_ACCOUNT") < 0


def test_dialog_shows_budget_remaining_and_account_balance(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    database: Database,
    ui_world: UiWorld,
) -> None:
    booking_control.update(planning_enabled=True, current_year=2026, current_month=5)
    _set_budget(database, ui_world.cc_a, 10000)
    first = _dialog(bookings, master_data, ui_world)
    _choose(first, ui_world.cc_a, ui_world.giro)
    first.soll_edit.setText("30,00")
    _save(first)

    dialog = _dialog(bookings, master_data, ui_world)
    _choose(dialog, ui_world.cc_a, ui_world.giro)

    assert "Haushaltsrest: 70,00 €" in dialog.leading_info.text()
    assert "Ansatz 100,00 €" in dialog.leading_info.text()
    assert "Monatsplan" in dialog.leading_info.text()
    assert "Rückstellung" in dialog.leading_info.text()
    assert "Kontostand" in dialog.second_info.text()
    assert "-30,00 €" in dialog.second_info.text()


def test_dialog_marks_free_and_blocked_months(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    database: Database,
    ui_world: UiWorld,
) -> None:
    with database.session_factory() as session:
        session.add(
            PeriodClosureModel(
                year=2026,
                month=4,
                closed_on=date(2026, 4, 30),
                closed_by_user_id=ui_world.actor,
                signature="x" * 64,
            )
        )
        session.commit()
    dialog = _dialog(bookings, master_data, ui_world)
    assert "offen (frei)" in dialog.period_label.text()

    dialog.booking_date_edit.setDate(QDate(2026, 4, 10))
    assert "abgeschlossen (fix)" in dialog.period_label.text()

    dialog.booking_date_edit.setDate(QDate(2026, 9, 1))
    assert "außerhalb" in dialog.period_label.text()


def test_dialog_shows_budget_block_message_and_saves_nothing(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    database: Database,
    ui_world: UiWorld,
) -> None:
    booking_control.update(planning_enabled=True, current_year=2026, current_month=5)
    _set_budget(database, ui_world.cc_a, 1000)
    dialog = _dialog(bookings, master_data, ui_world)
    _choose(dialog, ui_world.cc_a, ui_world.giro)
    dialog.soll_edit.setText("10,01")
    _save(dialog)

    assert "reicht nicht aus" in dialog.error_label.text()
    assert "0,01 €" in dialog.error_label.text()
    assert bookings.list_bookings(year=2026) == []


def test_dialog_warns_when_the_plan_year_of_the_origin_date_is_not_usable(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    warnings: list[str],
    ui_world: UiWorld,
) -> None:
    booking_control.update(planning_enabled=True, current_year=2026, current_month=5)
    dialog = _dialog(bookings, master_data, ui_world)
    _choose(dialog, ui_world.cc_a, ui_world.giro)
    dialog.soll_edit.setText("10,00")

    dialog.origin_date_edit.setDate(QDate(2025, 12, 20))
    assert "kein Plan" in dialog.leading_info.text()

    _save(dialog)

    assert len(warnings) == 1 and "kein Plan" in warnings[0]
    assert "kein Plan" in dialog.error_label.text()
    assert bookings.list_bookings(year=2026) == []


def test_list_shows_the_origin_date_column(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    dialog = _dialog(bookings, master_data, ui_world)
    _choose(dialog, ui_world.cc_a, ui_world.giro)
    dialog.soll_edit.setText("10,00")
    dialog.origin_date_edit.setDate(QDate(2026, 3, 20))
    _save(dialog)

    listing = _list(bookings, master_data, booking_control, ui_world)

    row = _cells(listing, 0)
    assert listing.table.horizontalHeaderItem(8).text() == "Entstehung"  # type: ignore[union-attr]
    assert row[8] == "20.03.2026"
    assert row[-1] == "offen"


def test_dialog_shows_a_notice_when_the_reserve_is_not_sufficient_but_still_books(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    planning: PlanningService,
    ui_world: UiWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planning.save_plan(
        ui_world.cc_a, 2026, base_budget_cents=120000, months=[], actor_id=ui_world.actor
    )
    notices: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda _parent, _title, text: notices.append(text) or None
    )
    dialog = _dialog(bookings, master_data, ui_world)
    _choose(dialog, ui_world.cc_a, ui_world.giro)
    dialog.origin_date_edit.setDate(QDate(2026, 1, 20))
    dialog.soll_edit.setText("250,00")
    assert "Rückstellungsbestand" in dialog.leading_info.text()

    _save(dialog)

    assert len(notices) == 1
    assert "01/2026" in notices[0] and "150,00 €" in notices[0]
    assert len(bookings.list_bookings(year=2026)) == 1


def test_dialog_shows_no_notice_without_reserve(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    ui_world: UiWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notices: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda _parent, _title, text: notices.append(text) or None
    )
    dialog = _dialog(bookings, master_data, ui_world)
    _choose(dialog, ui_world.cc_a, ui_world.giro)
    dialog.soll_edit.setText("250,00")

    _save(dialog)

    assert notices == []


def test_budget_transfer_preset_locks_the_type_and_transfers(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    database: Database,
    ui_world: UiWorld,
) -> None:
    booking_control.update(planning_enabled=True, current_year=2026, current_month=5)
    _set_budget(database, ui_world.cc_a, 10000)
    _set_budget(database, ui_world.cc_b, 0)
    dialog = _dialog(bookings, master_data, ui_world, preset=BookingType.BUDGET_TRANSFER)
    assert dialog.windowTitle() == "Ansatzumbuchung"
    assert dialog.type_combo.isEnabled() is False
    assert dialog.booking_type() is BookingType.BUDGET_TRANSFER

    _choose(dialog, ui_world.cc_a, ui_world.cc_b)
    dialog.soll_edit.setText("30,00")
    _save(dialog)

    first = bookings.cost_center_info(ui_world.cc_a, date(2026, 5, 10))
    second = bookings.cost_center_info(ui_world.cc_b, date(2026, 5, 10))
    assert (first.annual_budget_cents, second.annual_budget_cents) == (7000, 3000)


def test_edit_dialog_loads_and_updates_the_booking(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    seed = _dialog(bookings, master_data, ui_world)
    _choose(seed, ui_world.cc_a, ui_world.giro)
    seed.haben_edit.setText("-8,00")
    seed.merchant_edit.setText("Alt")
    _save(seed)
    (view,) = bookings.list_bookings(year=2026)

    dialog = _dialog(bookings, master_data, ui_world, booking_id=view.id)
    assert dialog.windowTitle() == "Buchung bearbeiten"
    assert dialog.haben_edit.text() == "-8,00 €"
    assert dialog.soll_edit.isEnabled() is False
    assert dialog.leading_combo.currentData() == ui_world.cc_a
    assert dialog.merchant_edit.text() == "Alt"

    dialog.haben_edit.setText("-9,00")
    dialog.merchant_edit.setText("Neu")
    _save(dialog)

    (updated,) = bookings.list_bookings(year=2026)
    assert (updated.amount_cents, updated.entry_side, updated.merchant) == (
        -900,
        Side.CREDIT,
        "Neu",
    )


# Buchungsliste


def _select_id(dialog: BookingListDialog, booking_id: str) -> None:
    for row in range(dialog.table.rowCount()):
        item = dialog.table.item(row, 0)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == booking_id:
            dialog.table.selectRow(row)
            return
    raise AssertionError("Zeile nicht gefunden")


def _list(
    bookings: BookingService,
    master_data: MasterDataService,
    control: BookingControlService,
    world: UiWorld,
) -> BookingListDialog:
    return BookingListDialog(bookings, master_data, control, world.actor)


def _cells(dialog: BookingListDialog, row: int) -> list[str]:
    return [dialog.table.item(row, column).text() for column in range(dialog.table.columnCount())]  # type: ignore[union-attr]


def test_list_shows_amounts_in_soll_or_haben_and_status(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    database: Database,
    ui_world: UiWorld,
) -> None:
    for side, text in (("soll_edit", "10,00"), ("haben_edit", "-2,50")):
        dialog = _dialog(bookings, master_data, ui_world)
        _choose(dialog, ui_world.cc_a, ui_world.giro)
        getattr(dialog, side).setText(text)
        _save(dialog)

    listing = _list(bookings, master_data, booking_control, ui_world)

    assert listing.table.rowCount() == 2
    rows = [_cells(listing, row) for row in range(2)]
    assert rows[0][1] == "Kostenstelle → Konto"
    assert (rows[0][4], rows[0][5]) == ("10,00 €", "")
    assert (rows[1][4], rows[1][5]) == ("", "-2,50 €")
    assert rows[0][-1] == "offen"
    assert "05/2026" in listing.status_label.text()
    assert "nicht aktiv" in listing.status_label.text()


def test_list_marks_closed_months_and_limits_actions(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    database: Database,
    ui_world: UiWorld,
) -> None:
    dialog = _dialog(bookings, master_data, ui_world)
    dialog.booking_date_edit.setDate(QDate(2026, 4, 20))
    _choose(dialog, ui_world.cc_a, ui_world.giro)
    dialog.soll_edit.setText("5,00")
    _save(dialog)
    with database.session_factory() as session:
        session.add(
            PeriodClosureModel(
                year=2026,
                month=4,
                closed_on=date(2026, 4, 30),
                closed_by_user_id=ui_world.actor,
                signature="x" * 64,
            )
        )
        session.commit()

    listing = _list(bookings, master_data, booking_control, ui_world)
    listing.month_combo.setCurrentIndex(0)  # Alle Monate
    (view,) = bookings.list_bookings(year=2026)
    _select_id(listing, view.id)

    assert _cells(listing, 0)[-1] == "abgeschlossen"
    assert listing.edit_button.isEnabled() is False
    assert listing.delete_button.isEnabled() is False
    assert listing.reverse_button.isEnabled() is True


def test_list_deletes_and_reverses_with_confirmation(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    ui_world: UiWorld,
    confirm_yes: None,
) -> None:
    for amount in ("10,00", "20,00"):
        dialog = _dialog(bookings, master_data, ui_world)
        _choose(dialog, ui_world.cc_a, ui_world.giro)
        dialog.soll_edit.setText(amount)
        _save(dialog)
    first, second = bookings.list_bookings(year=2026)
    listing = _list(bookings, master_data, booking_control, ui_world)

    _select_id(listing, first.id)
    listing.delete_button.click()
    assert [v.id for v in bookings.list_bookings(year=2026)] == [second.id]

    _select_id(listing, second.id)
    listing.reverse_button.click()
    views = bookings.list_bookings(year=2026)
    assert len(views) == 2
    reversal = next(view for view in views if view.is_reversal)
    assert (reversal.amount_cents, reversal.entry_side) == (-2000, Side.DEBIT)
    assert bookings.account_balance(ui_world.giro) == 0
    assert any("storniert" in _cells(listing, row)[-1] for row in range(listing.table.rowCount()))
    _select_id(listing, second.id)
    assert listing.reverse_button.isEnabled() is False
    assert listing.edit_button.isEnabled() is False


def test_list_filters_by_month(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    for day in (QDate(2026, 5, 3), QDate(2026, 6, 3)):
        dialog = _dialog(bookings, master_data, ui_world)
        dialog.booking_date_edit.setDate(day)
        _choose(dialog, ui_world.cc_a, ui_world.giro)
        dialog.soll_edit.setText("1,00")
        _save(dialog)
    listing = _list(bookings, master_data, booking_control, ui_world)
    assert listing.table.rowCount() == 1

    listing.month_combo.setCurrentIndex(0)
    assert listing.table.rowCount() == 2
    listing.month_combo.setCurrentIndex(6)
    assert listing.table.rowCount() == 1
    assert _cells(listing, 0)[0] == "03.06.2026"


# Umbuchung zwischen Konten mit Kostenstellen


def _transfer_dialog(
    bookings: BookingService,
    master_data: MasterDataService,
    world: UiWorld,
    transfer_id: str | None = None,
) -> TransferDialog:
    return TransferDialog(bookings, master_data, world.actor, transfer_id)


def _fill_transfer(dialog: TransferDialog, world: UiWorld, amount: str) -> None:
    for combo, entity_id in (
        (dialog.leading_account_combo, world.giro),
        (dialog.leading_cost_center_combo, world.cc_a),
        (dialog.transfer_account_combo, world.savings),
        (dialog.transfer_cost_center_combo, world.cc_b),
    ):
        combo.setCurrentIndex(combo.findData(entity_id))
    dialog.amount_edit.setText(amount)


def test_transfer_dialog_books_two_bookings(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    dialog = _transfer_dialog(bookings, master_data, ui_world)
    _fill_transfer(dialog, ui_world, "25,00")
    assert "Kontostand" in dialog.leading_account_info.text()
    _save(dialog)

    views = bookings.list_bookings(year=2026)
    assert [(v.entry_side, v.leading_label, v.second_label) for v in views] == [
        (Side.DEBIT, "100 Lebensmittel", "1000 Girokonto"),
        (Side.CREDIT, "200 Reisen", "2000 Sparkonto"),
    ]
    assert bookings.account_balance(ui_world.giro) == -2500
    assert bookings.account_balance(ui_world.savings) == 2500


def test_transfer_dialog_validates_input(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    ui_world: UiWorld,
) -> None:
    dialog = _transfer_dialog(bookings, master_data, ui_world)
    _fill_transfer(dialog, ui_world, "")
    _save(dialog)
    assert "Betrag" in dialog.error_label.text()

    _fill_transfer(dialog, ui_world, "5,00")
    dialog.transfer_account_combo.setCurrentIndex(
        dialog.transfer_account_combo.findData(ui_world.giro)
    )
    _save(dialog)
    assert "verschieden" in dialog.error_label.text()
    assert bookings.list_bookings(year=2026) == []


def test_list_edits_deletes_and_reverses_a_transfer_as_a_whole(
    qapp: QApplication,
    bookings: BookingService,
    booking_control: BookingControlService,
    master_data: MasterDataService,
    ui_world: UiWorld,
    confirm_yes: None,
) -> None:
    dialog = _transfer_dialog(bookings, master_data, ui_world)
    _fill_transfer(dialog, ui_world, "25,00")
    _save(dialog)
    debit, credit = bookings.list_bookings(year=2026)
    assert debit.transfer_id is not None and debit.transfer_id == credit.transfer_id
    listing = _list(bookings, master_data, booking_control, ui_world)
    assert _cells(listing, 0)[1] == TRANSFER_LABEL

    editor = _transfer_dialog(bookings, master_data, ui_world, debit.transfer_id)
    assert editor.amount_edit.text() == "25,00 €"
    assert editor.leading_account_combo.currentData() == ui_world.giro
    assert editor.transfer_cost_center_combo.currentData() == ui_world.cc_b
    editor.amount_edit.setText("40,00")
    _save(editor)
    assert bookings.account_balance(ui_world.savings) == 4000

    _select_id(listing, credit.id)
    listing.reverse_button.click()
    assert len(bookings.list_bookings(year=2026)) == 4
    assert bookings.account_balance(ui_world.giro) == 0
    assert bookings.account_balance(ui_world.savings) == 0

    _select_id(listing, debit.id)
    assert listing.edit_button.isEnabled() is False
    reversal = next(v for v in bookings.list_bookings(year=2026) if v.is_reversal)
    _select_id(listing, reversal.id)
    listing.delete_button.click()
    assert len(bookings.list_bookings(year=2026)) == 2
    assert bookings.account_balance(ui_world.giro) == -4000


# Buchungssteuerung


def test_control_dialog_saves_month_and_planning(
    qapp: QApplication,
    booking_control: BookingControlService,
    ui_world: UiWorld,
) -> None:
    dialog = BookingControlDialog(booking_control, ui_world.actor)
    assert dialog.year_spin.value() == 2026
    assert dialog.month_combo.currentData() == 5
    assert dialog.planning_check.isChecked() is False

    dialog.month_combo.setCurrentIndex(dialog.month_combo.findData(8))
    dialog.planning_check.setChecked(True)
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()

    control = booking_control.get()
    assert (control.current_month, control.planning_enabled) == (8, True)
