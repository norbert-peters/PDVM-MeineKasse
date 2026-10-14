import os
from collections.abc import Callable
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from conftest import World  # noqa: E402
from meine_kasse.application.services.booking_control_service import (  # noqa: E402
    BookingControlService,
)
from meine_kasse.application.services.booking_service import BookingService  # noqa: E402
from meine_kasse.application.services.master_data_service import MasterDataService  # noqa: E402
from meine_kasse.application.services.user_settings_service import (  # noqa: E402
    TableSort,
    UserSettingsService,
)
from meine_kasse.domain.enums import AccountType, BookingType, ObjectKind, Side  # noqa: E402
from meine_kasse.domain.repositories import UnitOfWork  # noqa: E402
from meine_kasse.domain.services.booking_rules import Stelle  # noqa: E402
from meine_kasse.presentation.dialogs.account_dialogs import AccountListDialog  # noqa: E402
from meine_kasse.presentation.dialogs.booking_list_dialog import BookingListDialog  # noqa: E402
from meine_kasse.presentation.widgets.data_table import (  # noqa: E402
    AUTO,
    DataTable,
    SortItem,
    TablePreferences,
)

_AMOUNT = 4
_DATE = 0


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


@pytest.fixture
def preferences(uow_factory: Callable[[], UnitOfWork], world: World) -> TablePreferences:
    return TablePreferences(UserSettingsService(uow_factory), world.actor)


def _fill(table: DataTable, rows: list[tuple[str, str]]) -> None:
    table.table.setRowCount(len(rows))
    for index, (key, amount) in enumerate(rows):
        table.table.setItem(index, 0, SortItem(key, row_id=key))
        table.table.setItem(index, 1, SortItem(amount))
    table.apply()


def _column(table: DataTable, column: int) -> list[str]:
    return [
        table.table.item(row, column).text()  # type: ignore[union-attr]
        for row in range(table.table.rowCount())
        if not table.table.isRowHidden(row)
    ]


# Tabellenkomponente


def test_sorts_amounts_by_value_and_toggles_direction(qapp: QApplication) -> None:
    table = DataTable(["Name", "Betrag"], table_key="t")
    _fill(table, [("a", "10,00 €"), ("b", "9,00 €"), ("c", "-2,50 €")])

    table.table.horizontalHeader().sectionClicked.emit(1)
    assert _column(table, 1) == ["-2,50 €", "9,00 €", "10,00 €"]

    table.table.horizontalHeader().sectionClicked.emit(1)
    assert _column(table, 1) == ["10,00 €", "9,00 €", "-2,50 €"]
    assert table.sort == TableSort("Betrag", ascending=False)


def test_without_sort_the_given_order_is_kept(qapp: QApplication) -> None:
    table = DataTable(["Name", "Betrag"], table_key="t")

    _fill(table, [("b", "2,00 €"), ("a", "1,00 €")])

    assert _column(table, 0) == ["b", "a"]
    assert table.sort is None


def test_column_filter_hides_rows_and_combines_columns(qapp: QApplication) -> None:
    table = DataTable(["Name", "Betrag"], table_key="t")
    _fill(table, [("Volksbank Gebühr", "1,00 €"), ("Gebühr Sparda", "2,00 €"), ("Miete", "3,00 €")])

    table.filter_edit(0).setText("GEB")
    assert _column(table, 0) == ["Volksbank Gebühr", "Gebühr Sparda"]

    table.filter_edit(1).setText("2,00")
    assert _column(table, 0) == ["Gebühr Sparda"]
    assert table.visible_rows() == [["Gebühr Sparda", "2,00 €"]]

    table.filter_edit(0).clear()
    table.filter_edit(1).clear()
    assert len(_column(table, 0)) == 3


def test_filter_applies_to_rows_added_later_and_to_sorted_view(qapp: QApplication) -> None:
    table = DataTable(["Name", "Betrag"], table_key="t")
    table.filter_edit(0).setText("a")
    table.set_sort("Betrag", ascending=False, save=False)

    _fill(table, [("alpha", "1,00 €"), ("beta", "3,00 €"), ("kilo", "2,00 €")])

    assert _column(table, 1) == ["3,00 €", "1,00 €"]


def test_hiding_the_selected_row_clears_the_selection(qapp: QApplication) -> None:
    table = DataTable(["Name", "Betrag"], table_key="t")
    _fill(table, [("a", "1,00 €"), ("b", "2,00 €")])
    table.select_id("b")
    assert table.selected_id() == "b"

    table.filter_edit(0).setText("a")

    assert table.selected_id() is None


def test_selection_follows_the_row_after_sorting(qapp: QApplication) -> None:
    table = DataTable(["Name", "Betrag"], table_key="t")
    _fill(table, [("a", "5,00 €"), ("b", "1,00 €")])
    table.select_id("a")

    table.set_sort("Betrag", save=False)

    assert table.selected_id() == "a"


def test_explicit_sort_values_win_over_display_text(qapp: QApplication) -> None:
    table = DataTable(["Name", "Betrag"], table_key="t")
    table.table.setRowCount(2)
    table.table.setItem(0, 0, SortItem("zweiter", sort_value=2, row_id="x"))
    table.table.setItem(1, 0, SortItem("erster", sort_value=1, row_id="y"))

    table.set_sort("Name", save=False)

    assert _column(table, 0) == ["erster", "zweiter"]


def test_unknown_sort_column_is_rejected(qapp: QApplication) -> None:
    table = DataTable(["Name"], table_key="t")

    with pytest.raises(ValueError):
        table.set_sort("gibt es nicht")


def test_sort_is_saved_per_user_and_restored(
    qapp: QApplication, preferences: TablePreferences
) -> None:
    first = DataTable(["Name", "Betrag"], table_key="liste", preferences=preferences)
    first.set_sort("Betrag", ascending=False)

    second = DataTable(["Name", "Betrag"], table_key="liste", preferences=preferences)
    other_table = DataTable(["Name", "Betrag"], table_key="andere", preferences=preferences)

    assert second.sort == TableSort("Betrag", ascending=False)
    assert other_table.sort is None


def test_saved_sort_of_a_removed_column_is_ignored(
    qapp: QApplication, preferences: TablePreferences
) -> None:
    DataTable(["Name", "Alt"], table_key="liste", preferences=preferences).set_sort("Alt")

    table = DataTable(["Name", "Neu"], table_key="liste", preferences=preferences)

    assert table.sort is None


def test_default_sentinel_derives_key_from_text(qapp: QApplication) -> None:
    assert SortItem("9,00 €", sort_value=AUTO) < SortItem("10,00 €")


# Buchungsliste und Stammdatenliste


def _post(bookings: BookingService, world: World, day: date, cents: int, side: Side) -> None:
    bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=side,
        amount_cents=cents,
        booking_date=day,
        origin_date=day,
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        actor_id=world.actor,
    )


def _booking_list(
    bookings: BookingService,
    master_data: MasterDataService,
    booking_control: BookingControlService,
    world: World,
    preferences: TablePreferences | None,
) -> BookingListDialog:
    dialog = BookingListDialog(
        bookings, master_data, booking_control, world.actor, preferences=preferences
    )
    dialog.month_combo.setCurrentIndex(0)  # Alle Monate
    return dialog


def test_booking_list_sorts_by_raw_amount_and_date_and_remembers_it(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    booking_control: BookingControlService,
    world: World,
    preferences: TablePreferences,
) -> None:
    _post(bookings, world, date(2026, 4, 20), 900, Side.DEBIT)
    _post(bookings, world, date(2026, 5, 2), 1000, Side.DEBIT)
    _post(bookings, world, date(2026, 6, 1), 150, Side.DEBIT)
    listing = _booking_list(bookings, master_data, booking_control, world, preferences)

    listing.data_table.set_sort("Soll")
    assert _column(listing.data_table, _AMOUNT) == ["1,50 €", "9,00 €", "10,00 €"]

    listing.data_table.set_sort("Datum", ascending=False)
    assert _column(listing.data_table, _DATE) == ["01.06.2026", "02.05.2026", "20.04.2026"]

    reopened = _booking_list(bookings, master_data, booking_control, world, preferences)
    assert reopened.data_table.sort == TableSort("Datum", ascending=False)
    assert _column(reopened.data_table, _DATE)[0] == "01.06.2026"


def test_booking_list_keeps_selection_and_actions_with_sorting_and_filter(
    qapp: QApplication,
    bookings: BookingService,
    master_data: MasterDataService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    _post(bookings, world, date(2026, 5, 2), 1000, Side.DEBIT)
    _post(bookings, world, date(2026, 5, 3), 200, Side.CREDIT)
    listing = _booking_list(bookings, master_data, booking_control, world, None)
    listing.data_table.set_sort("Datum", ascending=False, save=False)
    listing.data_table.select_id(next(iter(listing._views)))
    assert listing.edit_button.isEnabled()

    listing.data_table.filter_edit(5).setText("zzz")  # Haben: nichts passt

    assert listing.selected_id() is None
    assert not listing.edit_button.isEnabled()
    assert listing.data_table.visible_rows() == []


def test_account_list_sorts_numbers_naturally(
    qapp: QApplication,
    master_data: MasterDataService,
    world: World,
    preferences: TablePreferences,
) -> None:
    master_data.create_account(number="300", name="Tagesgeld", account_type=AccountType.SAVINGS)
    dialog = AccountListDialog(master_data, world.actor, preferences=preferences)

    dialog.data_table.set_sort("Nummer")

    assert _column(dialog.data_table, 0) == ["300", "1000", "2000"]
