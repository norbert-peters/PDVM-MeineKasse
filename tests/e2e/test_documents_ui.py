import os
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from conftest import World  # noqa: E402
from meine_kasse.application.services.auth_service import AuthService, LoginResult  # noqa: E402
from meine_kasse.application.services.backup_service import BackupService  # noqa: E402
from meine_kasse.application.services.booking_control_service import (  # noqa: E402
    BookingControlService,
)
from meine_kasse.application.services.booking_service import BookingService  # noqa: E402
from meine_kasse.application.services.closing_service import ClosingService  # noqa: E402
from meine_kasse.application.services.document_service import DocumentService  # noqa: E402
from meine_kasse.application.services.master_data_service import MasterDataService  # noqa: E402
from meine_kasse.application.services.opening_balance_service import (  # noqa: E402
    OpeningBalanceService,
)
from meine_kasse.application.services.planning_service import PlanningService  # noqa: E402
from meine_kasse.application.services.report_service import ReportService  # noqa: E402
from meine_kasse.application.services.user_service import UserService  # noqa: E402
from meine_kasse.application.services.user_settings_service import (  # noqa: E402
    UserSettingsService,
)
from meine_kasse.domain.entities import ReportDefinition  # noqa: E402
from meine_kasse.domain.enums import (  # noqa: E402
    BookingType,
    FilterOperator,
    ObjectKind,
    ReportSource,
    Side,
)
from meine_kasse.domain.repositories import UnitOfWork  # noqa: E402
from meine_kasse.domain.services.booking_rules import Stelle  # noqa: E402
from meine_kasse.infrastructure.database.session import Database  # noqa: E402
from meine_kasse.infrastructure.reporting.pdf_renderer import ReportlabPdfRenderer  # noqa: E402
from meine_kasse.presentation.dialogs.account_dialogs import AccountListDialog  # noqa: E402
from meine_kasse.presentation.dialogs.booking_list_dialog import BookingListDialog  # noqa: E402
from meine_kasse.presentation.dialogs.document_archive_dialog import (  # noqa: E402
    DocumentArchiveDialog,
    format_size,
)
from meine_kasse.presentation.dialogs.report_dialog import ReportDialog  # noqa: E402
from meine_kasse.presentation.main_window import MainWindow  # noqa: E402
from meine_kasse.presentation.widgets.data_table import (  # noqa: E402
    DataTable,
    SortItem,
    TablePreferences,
)
from meine_kasse.presentation.widgets.pdf_export import PdfExporter  # noqa: E402

D = date(2026, 5, 10)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


@pytest.fixture
def documents(
    uow_factory: Callable[[], UnitOfWork], tmp_path: Path, world: World
) -> DocumentService:
    return DocumentService(uow_factory, ReportlabPdfRenderer(), tmp_path / "Dokumente")


@pytest.fixture
def reports(
    uow_factory: Callable[[], UnitOfWork], planning: PlanningService, documents: DocumentService
) -> ReportService:
    return ReportService(uow_factory, planning, documents)


@pytest.fixture
def exporter(
    documents: DocumentService, world: World, monkeypatch: pytest.MonkeyPatch
) -> PdfExporter:
    pdf = PdfExporter(documents, world.actor)
    monkeypatch.setattr(PdfExporter, "ask_suffix", lambda _self, _parent: "Test")
    monkeypatch.setattr(PdfExporter, "offer_open", lambda _self, _parent, _view: None)
    return pdf


@pytest.fixture
def preferences(
    uow_factory: Callable[[], UnitOfWork], world: World, exporter: PdfExporter
) -> TablePreferences:
    return TablePreferences(UserSettingsService(uow_factory), world.actor, exporter)


def _post(bookings: BookingService, world: World, cents: int, text: str = "Einkauf") -> None:
    bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=Side.DEBIT,
        amount_cents=cents,
        booking_date=D,
        origin_date=D,
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        booking_text=text,
        actor_id=world.actor,
    )


# Tabellenkomponente


def test_table_pdf_contains_visible_rows_in_display_order(qapp: QApplication) -> None:
    table = DataTable(["Name", "Betrag"], table_key="t")
    table.table.setRowCount(3)
    for index, (name, amount) in enumerate([("a", "10,00 €"), ("b", "9,00 €"), ("c", "-2,50 €")]):
        table.table.setItem(index, 0, SortItem(name))
        item = SortItem(amount)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.table.setItem(index, 1, item)
    table.apply()
    table.set_sort("Betrag")
    table.filter_edit(0).setText("b")

    pdf = table.pdf_table("Liste", ["Zeitraum: Mai 2026"])

    assert [row.cells for row in pdf.rows] == [("b", "9,00 €")]
    assert [column.header for column in pdf.columns] == ["Name", "Betrag"]
    assert [column.align_right for column in pdf.columns] == [False, True]
    assert pdf.subtitle_lines[0] == "Zeitraum: Mai 2026"
    assert any(line.startswith("Filter:") and "Name" in line for line in pdf.subtitle_lines)
    assert "Sortierung: Betrag aufsteigend" in pdf.subtitle_lines
    assert pdf.subtitle_lines[-1] == "1 Zeilen"


def test_pdf_button_exists_only_with_an_exporter(
    qapp: QApplication, preferences: TablePreferences, uow_factory: Callable[[], UnitOfWork]
) -> None:
    assert DataTable(["A"], table_key="t").pdf_button("Liste") is None
    plain = TablePreferences(UserSettingsService(uow_factory), "x")
    assert DataTable(["A"], table_key="t", preferences=plain).pdf_button("Liste") is None
    assert DataTable(["A"], table_key="t", preferences=preferences).pdf_button("Liste") is not None


def test_booking_list_exports_the_displayed_table_to_the_archive(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    booking_control: BookingControlService,
    documents: DocumentService,
    preferences: TablePreferences,
    world: World,
) -> None:
    _post(bookings, world, 1000)
    _post(bookings, world, 250, text="Anderes")
    dialog = BookingListDialog(
        bookings, master_data, booking_control, world.actor, preferences=preferences
    )
    dialog.data_table.filter_edit(7).setText("Anderes")

    buttons = [b for b in dialog.findChildren(type(dialog.new_button)) if b.text() == "&PDF…"]
    assert len(buttons) == 1
    buttons[0].click()

    (archived,) = documents.list_documents()
    assert archived.name == "Buchungen"
    assert archived.file_name.endswith("_Buchungen_Test.pdf")
    assert documents.path_of(archived.id).read_bytes().startswith(b"%PDF-")


def test_master_list_offers_pdf_output(
    qapp: QApplication,
    master_data: MasterDataService,
    preferences: TablePreferences,
    documents: DocumentService,
    world: World,
) -> None:
    dialog = AccountListDialog(master_data, world.actor, preferences=preferences)
    assert dialog.pdf_button is not None
    dialog.refresh()

    dialog.pdf_button.click()

    (archived,) = documents.list_documents()
    assert archived.file_name.endswith("_Konten_Test.pdf") or "Konten" in archived.file_name


# Auswertungsdialog


def test_report_dialog_runs_filters_and_shows_total_first(
    qapp: QApplication,
    reports: ReportService,
    exporter: PdfExporter,
    bookings: BookingService,
    world: World,
) -> None:
    _post(bookings, world, 1000)
    _post(bookings, world, 2500)
    dialog = ReportDialog(reports, exporter, world.actor)
    assert dialog.source_combo.currentData() == ReportSource.BOOKINGS

    dialog.run()

    assert dialog.table.rowCount() == 3
    labels = [
        dialog.table.horizontalHeaderItem(index).text()  # type: ignore[union-attr]
        for index in range(dialog.table.columnCount())
    ]
    assert "Soll" in labels
    soll = labels.index("Soll")
    assert dialog.table.item(0, soll).text() == "35,00 €"  # type: ignore[union-attr]
    assert dialog.pdf_button.isEnabled()

    dialog._add_filter()
    row = dialog._filter_rows[0]
    row.column_combo.setCurrentIndex(row.column_combo.findData("debit"))
    row.operator_combo.setCurrentIndex(row.operator_combo.findData(FilterOperator.GREATER.value))
    row.value_edit.setText("20,00")
    dialog.run()

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, soll).text() == "25,00 €"  # type: ignore[union-attr]


def test_report_dialog_shows_validation_errors(
    qapp: QApplication, reports: ReportService, exporter: PdfExporter, world: World
) -> None:
    dialog = ReportDialog(reports, exporter, world.actor)
    for index in range(dialog.column_list.count()):
        dialog.column_list.item(index).setCheckState(Qt.CheckState.Unchecked)

    dialog.run()

    assert "mindestens eine Spalte" in dialog.message_label.text()
    assert dialog.table.rowCount() == 0
    assert not dialog.pdf_button.isEnabled()


def test_report_dialog_saves_loads_and_deletes_definitions(
    qapp: QApplication,
    reports: ReportService,
    exporter: PdfExporter,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = ReportDialog(reports, exporter, world.actor)
    dialog.source_combo.setCurrentIndex(dialog.source_combo.findData(ReportSource.ACCOUNTS.value))
    dialog.sort_combo.setCurrentIndex(dialog.sort_combo.findData("account"))
    dialog.group_combos[0].setCurrentIndex(dialog.group_combos[0].findData("account_type"))
    dialog.group_summary_only[0].setChecked(True)
    dialog._add_filter()
    dialog._filter_rows[0].column_combo.setCurrentIndex(0)
    dialog._filter_rows[0].value_edit.setText("giro")
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: ("Kontenübersicht", True))

    dialog._save()

    assert [item.name for item in reports.list_definitions(world.actor)] == ["Kontenübersicht"]
    assert dialog.saved_combo.currentData() == "Kontenübersicht"

    reopened = ReportDialog(reports, exporter, world.actor)
    reopened.saved_combo.setCurrentIndex(reopened.saved_combo.findData("Kontenübersicht"))
    reopened._load_saved()
    assert reopened.source_combo.currentData() == ReportSource.ACCOUNTS
    assert reopened.sort_combo.currentData() == "account"
    assert reopened.group_combos[0].currentData() == "account_type"
    assert reopened.group_summary_only[0].isChecked()
    assert reopened._filter_rows[0].value_edit.text() == "giro"
    assert reopened._filter_rows[0].operator_combo.currentData() == "CONTAINS"

    reopened.run()
    assert reopened.last_result is not None
    assert reopened.last_result.row_count == 1

    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    reopened._delete()
    assert reports.list_definitions(world.actor) == []


def test_report_dialog_exports_pdf_to_the_archive(
    qapp: QApplication,
    reports: ReportService,
    exporter: PdfExporter,
    documents: DocumentService,
    bookings: BookingService,
    world: World,
) -> None:
    _post(bookings, world, 1000)
    dialog = ReportDialog(reports, exporter, world.actor)
    dialog.run()

    dialog.pdf_button.click()

    (archived,) = documents.list_documents()
    assert archived.document_type.value == "REPORT"
    assert archived.file_name.endswith("_Buchungen_Test.pdf")


# Dokumentenarchiv und Hauptmenü


def test_archive_dialog_lists_documents_and_verifies_them(
    qapp: QApplication,
    exporter: PdfExporter,
    documents: DocumentService,
    reports: ReportService,
    world: World,
) -> None:
    view = reports.export_pdf(
        ReportDefinition("Konten", ReportSource.ACCOUNTS, ("account", "balance")),
        actor_id=world.actor,
    )
    dialog = DocumentArchiveDialog(exporter)

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "Konten"  # type: ignore[union-attr]
    assert dialog.table.item(0, 3).text() == "Auswertung"  # type: ignore[union-attr]
    assert not dialog.open_button.isEnabled()

    dialog.table.selectRow(0)
    dialog._verify()
    assert dialog.message_label.text() == "Datei unverändert"

    documents.path_of(view.id).write_bytes(b"manipuliert")
    dialog._verify()
    assert dialog.message_label.text() == "Datei verändert"

    documents.path_of(view.id).unlink()
    dialog.refresh()
    assert dialog.table.item(0, 6).text() == "Datei fehlt"  # type: ignore[union-attr]


def test_format_size() -> None:
    assert format_size(512) == "512 Byte"
    assert format_size(2048) == "2,0 KB"
    assert format_size(3 * 1024 * 1024) == "3,0 MB"


def test_main_window_has_report_menu_when_services_are_available(
    qapp: QApplication,
    auth: AuthService,
    master_data: MasterDataService,
    users: UserService,
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    closing: ClosingService,
    openings: OpeningBalanceService,
    database: Database,
    documents: DocumentService,
    reports: ReportService,
    tmp_path: Path,
) -> None:
    window = MainWindow(
        LoginResult("id", "Anna Muster", False),
        auth=auth,
        master_data=master_data,
        users=users,
        booking_control=booking_control,
        bookings=bookings,
        planning=planning,
        closing=closing,
        opening_balances=openings,
        backup=BackupService(database, tmp_path / "test.sqlite"),
        documents=documents,
        reports=reports,
    )

    titles = [action.text() for action in window.menuBar().actions()]
    assert "A&uswertung" in titles
    menu = window.menuBar().actions()[titles.index("A&uswertung")].menu()
    assert menu is not None
    assert [action.text() for action in menu.actions()] == ["Auswertung…", "Dokumentenarchiv…"]
