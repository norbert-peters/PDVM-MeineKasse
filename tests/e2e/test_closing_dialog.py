import os
from datetime import date

import pytest
from sqlalchemy import select

from conftest import World

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox  # noqa: E402

from meine_kasse.application.services.booking_control_service import (  # noqa: E402
    BookingControlService,
)
from meine_kasse.application.services.booking_service import BookingService  # noqa: E402
from meine_kasse.application.services.closing_service import ClosingService  # noqa: E402
from meine_kasse.domain.enums import BookingType, ClosureKind, ObjectKind, Side  # noqa: E402
from meine_kasse.domain.services.booking_rules import Stelle  # noqa: E402
from meine_kasse.domain.services.closing_rules import ClosureRef  # noqa: E402
from meine_kasse.infrastructure.database.models import (  # noqa: E402
    BookingModel,
    MonthlyActualModel,
)
from meine_kasse.infrastructure.database.session import Database  # noqa: E402
from meine_kasse.presentation.dialogs.closing_dialog import ClosingDialog  # noqa: E402
from meine_kasse.presentation.dialogs.reopen_closing_dialog import (  # noqa: E402
    ReopenClosingDialog,
    ReopeningHistoryDialog,
)

YEAR = 2026
MONTH_COLUMN, STATUS_COLUMN, DATE_COLUMN, SIGNATURE_COLUMN = 0, 1, 2, 3


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


@pytest.fixture
def confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)


@pytest.fixture
def infos(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda _parent, _title, text: messages.append(text) or None
    )
    return messages


def _dialog(closing: ClosingService, control: BookingControlService, world: World) -> ClosingDialog:
    return ClosingDialog(closing, control, world.actor)


def _cell(dialog: ClosingDialog, row: int, column: int) -> str:
    item = dialog.table.item(row, column)
    assert item is not None
    return item.text()


def _spend(bookings: BookingService, world: World, day: date) -> str:
    return bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=Side.DEBIT,
        amount_cents=5000,
        booking_date=day,
        origin_date=day,
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        actor_id=world.actor,
    )


def test_dialog_shows_the_current_period_and_twelve_open_months(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    dialog = _dialog(closing, booking_control, world)

    assert dialog.year_spin.value() == YEAR
    assert dialog.current_label.text() == "05/2026"
    assert dialog.year_label.text() == "offen (frei)"
    assert dialog.table.rowCount() == 12
    assert _cell(dialog, 4, STATUS_COLUMN) == "offen (frei) – aktueller Buchungsmonat"
    assert _cell(dialog, 0, STATUS_COLUMN) == "offen (frei)"
    assert dialog.close_month_button.isEnabled() is True
    assert dialog.close_year_button.isEnabled() is False
    assert "Offen: 01, 02" in dialog.blocker_label.text()


def test_closing_a_month_needs_confirmation_and_shows_the_signature(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
    confirm: None,
) -> None:
    _spend(bookings, world, date(2026, 5, 10))
    dialog = _dialog(closing, booking_control, world)
    dialog.close_month_button.click()

    assert "wurde abgeschlossen" in dialog.message_label.text()
    assert "06/2026" in dialog.message_label.text()
    assert dialog.current_label.text() == "06/2026"
    assert _cell(dialog, 4, STATUS_COLUMN) == "abgeschlossen (fix)"
    assert _cell(dialog, 4, DATE_COLUMN) == "15.05.2026"
    assert len(_cell(dialog, 4, SIGNATURE_COLUMN)) > 10
    assert _cell(dialog, 5, STATUS_COLUMN).startswith("offen (frei) – aktueller")
    assert closing.get_overview(YEAR).months[4].is_closed


def test_declining_the_confirmation_changes_nothing(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)
    dialog = _dialog(closing, booking_control, world)
    dialog.close_month_button.click()

    assert dialog.current_label.text() == "05/2026"
    assert closing.get_overview(YEAR).months[4].is_closed is False


def test_dialog_blocks_closing_when_months_would_be_skipped(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
    confirm: None,
) -> None:
    booking_control.update(planning_enabled=False, current_year=YEAR, current_month=1)
    first = _dialog(closing, booking_control, world)
    first.close_month_button.click()
    booking_control.update(planning_enabled=False, current_year=YEAR, current_month=4)

    dialog = _dialog(closing, booking_control, world)
    assert dialog.close_month_button.isEnabled() is False
    assert "02/2026" in dialog.blocker_label.text()


def test_dialog_reports_errors_of_the_consistency_check(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    database: Database,
    world: World,
    confirm: None,
) -> None:
    _spend(bookings, world, date(2026, 5, 10))
    with database.session_factory() as session:
        session.scalars(select(MonthlyActualModel)).one().debit_cents = 1
        session.commit()
    dialog = _dialog(closing, booking_control, world)
    dialog.close_month_button.click()

    assert "Ist-Fortschreibung" in dialog.message_label.text()
    assert dialog.current_label.text() == "05/2026"


def test_verification_reports_unchanged_and_changed_closures(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    database: Database,
    world: World,
    confirm: None,
    infos: list[str],
) -> None:
    booking_id = _spend(bookings, world, date(2026, 5, 10))
    dialog = _dialog(closing, booking_control, world)
    dialog.verify_button.click()
    assert infos[-1] == "Es gibt noch keine Abschlüsse."

    dialog.close_month_button.click()
    dialog.verify_button.click()
    assert "Alle 1 Abschlüsse sind unverändert" in dialog.message_label.text()
    assert "Signatur gültig" in infos[-1]

    with database.session_factory() as session:
        session.get(BookingModel, booking_id).amount_cents = 1  # type: ignore[union-attr]
        session.commit()
    dialog.verify_button.click()
    assert "weichen ab" in dialog.message_label.text()
    assert "ABWEICHEND" in infos[-1]


def test_year_can_be_closed_in_the_dialog_after_all_months(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
    confirm: None,
) -> None:
    booking_control.update(planning_enabled=False, current_year=YEAR, current_month=1)
    for _ in range(12):
        closing.close_month(actor_id=world.actor)

    dialog = _dialog(closing, booking_control, world)
    dialog.year_spin.setValue(YEAR)
    assert dialog.close_year_button.isEnabled() is True
    assert dialog.close_month_button.isEnabled() is True

    dialog.close_year_button.click()

    assert "wurde abgeschlossen" in dialog.message_label.text()
    assert dialog.year_label.text().startswith("abgeschlossen (fix)")
    assert dialog.close_year_button.isEnabled() is False
    assert _cell(dialog, 11, STATUS_COLUMN) == "abgeschlossen (fix)"


REASON = "Fehlbuchung wurde entdeckt"


def _fake_reopen_exec(monkeypatch: pytest.MonkeyPatch, reason: str = REASON) -> None:
    def fake_exec(self: ReopenClosingDialog) -> int:
        self.reason_edit.setPlainText(reason)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        return int(self.result())

    monkeypatch.setattr(ReopenClosingDialog, "exec", fake_exec)


def test_reopen_button_follows_the_latest_closure(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
    confirm: None,
) -> None:
    dialog = _dialog(closing, booking_control, world)
    assert dialog.reopen_button.isEnabled() is False
    assert dialog.reopen_label.text() == "kein Abschluss vorhanden"

    dialog.close_month_button.click()

    assert dialog.reopen_button.isEnabled() is True
    assert dialog.reopen_label.text() == "Monat 05/2026"


def test_reopening_in_the_dialog_documents_and_rewinds(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
    confirm: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = _dialog(closing, booking_control, world)
    dialog.close_month_button.click()
    _fake_reopen_exec(monkeypatch)

    dialog.reopen_button.click()

    assert "wiedereröffnet" in dialog.message_label.text()
    assert dialog.current_label.text() == "05/2026"
    assert _cell(dialog, 4, STATUS_COLUMN).startswith("offen (frei)")
    assert dialog.reopen_button.isEnabled() is False
    (entry,) = closing.list_reopenings()
    assert entry.reason == REASON


def test_reopen_dialog_requires_a_reason(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
    confirm: None,
) -> None:
    ClosingDialog(closing, booking_control, world.actor).close_month_button.click()
    dialog = ReopenClosingDialog(closing, ClosureRef(ClosureKind.MONTH, YEAR, 5), world.actor)
    dialog.reason_edit.setPlainText("kurz")
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()

    assert "Begründung" in dialog.error_label.text()
    assert closing.list_reopenings() == []
    assert closing.get_overview(YEAR).months[4].is_closed is True


def test_reopen_dialog_reports_the_required_order(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    booking_control.update(planning_enabled=False, current_year=YEAR, current_month=1)
    closing.close_month(actor_id=world.actor)
    closing.close_month(actor_id=world.actor)
    dialog = ReopenClosingDialog(closing, ClosureRef(ClosureKind.MONTH, YEAR, 1), world.actor)
    dialog.reason_edit.setPlainText(REASON)
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()

    assert "umgekehrter Reihenfolge" in dialog.error_label.text()
    assert "Monat 02/2026" in dialog.error_label.text()


def test_year_closing_is_reopened_first_in_the_dialog(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
    confirm: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    booking_control.update(planning_enabled=False, current_year=YEAR, current_month=1)
    for _ in range(12):
        closing.close_month(actor_id=world.actor)
    dialog = _dialog(closing, booking_control, world)
    dialog.year_spin.setValue(YEAR)
    dialog.close_year_button.click()
    assert dialog.reopen_label.text() == "Jahr 2026"
    _fake_reopen_exec(monkeypatch)

    dialog.reopen_button.click()

    assert dialog.year_label.text() == "offen (frei)"
    assert dialog.reopen_label.text() == "Monat 12/2026"


def test_history_dialog_lists_reopenings_with_signature_validity(
    qapp: QApplication,
    closing: ClosingService,
    booking_control: BookingControlService,
    bookings: BookingService,
    database: Database,
    world: World,
) -> None:
    booking_id = _spend(bookings, world, date(2026, 5, 10))
    closing.close_month(actor_id=world.actor)
    with database.session_factory() as session:
        session.get(BookingModel, booking_id).amount_cents = 1  # type: ignore[union-attr]
        session.commit()
    closing.reopen_month(YEAR, 5, reason=REASON, actor_id=world.actor)

    history = ReopeningHistoryDialog(closing)

    assert history.table.rowCount() == 1
    cells = [history.table.item(0, column).text() for column in range(6)]  # type: ignore[union-attr]
    assert cells[0] == "Monat 05/2026"
    assert cells[1] == "15.05.2026"
    assert cells[2] == "A A"
    assert cells[3] == REASON
    assert cells[4].startswith("15.05.2026")
    assert cells[5] == "Nein"
