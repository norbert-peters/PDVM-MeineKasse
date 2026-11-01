from datetime import date

import pytest

from meine_kasse.application.reporting.engine import run_report, validate_definition
from meine_kasse.application.reporting.pdf_model import RowStyle
from meine_kasse.domain.entities import ReportDefinition, ReportFilter, ReportGroup, ReportSort
from meine_kasse.domain.enums import FilterOperator, ReportSource
from meine_kasse.domain.errors import ValidationError


def booking(day: int, cost_center: str, debit: int | None, credit: int | None = None) -> dict:
    return {
        "booking_date": date(2026, 5, day),
        "cost_center": cost_center,
        "debit": debit,
        "credit": credit,
        "booking_text": f"Text {day}",
    }


ROWS = [
    booking(3, "200 Reisen", 3000),
    booking(1, "100 Lebensmittel", 1000),
    booking(2, "100 Lebensmittel", None, 250),
    booking(4, "100 Lebensmittel", 500),
]
COLUMNS = ("booking_date", "cost_center", "debit", "credit")


def definition(**changes: object) -> ReportDefinition:
    values: dict[str, object] = {
        "name": "Test",
        "data_source": ReportSource.BOOKINGS,
        "columns": COLUMNS,
    }
    values.update(changes)
    return ReportDefinition(**values)  # type: ignore[arg-type]


def texts(result, column: int) -> list[str]:
    return [row.cells[column] for row in result.rows]


def test_total_row_sums_only_additive_columns_with_sign() -> None:
    result = run_report(definition(), ROWS)

    assert result.total_row.style is RowStyle.TOTAL
    assert result.total_row.cells == ("Gesamt", "", "45,00 €", "2,50 €")
    assert result.row_count == 4


def test_empty_amounts_are_blank_and_dates_are_german() -> None:
    result = run_report(definition(sort=ReportSort("booking_date")), ROWS)

    assert texts(result, 0) == ["01.05.2026", "02.05.2026", "03.05.2026", "04.05.2026"]
    assert result.rows[1].cells[2] == ""
    assert result.rows[1].cells[3] == "2,50 €"


def test_sorts_by_raw_values_ascending_and_descending() -> None:
    ascending = run_report(definition(sort=ReportSort("debit")), ROWS)
    descending = run_report(definition(sort=ReportSort("debit", ascending=False)), ROWS)

    assert texts(ascending, 2) == ["", "5,00 €", "10,00 €", "30,00 €"]
    assert texts(descending, 2) == ["30,00 €", "10,00 €", "5,00 €", ""]


def test_filters_are_combined_with_and() -> None:
    result = run_report(
        definition(
            filters=(
                ReportFilter("cost_center", FilterOperator.CONTAINS, "lebens"),
                ReportFilter("debit", FilterOperator.GREATER_OR_EQUAL, "5,00"),
            )
        ),
        ROWS,
    )

    assert result.row_count == 2
    assert result.total_row.cells[2] == "15,00 €"


def test_date_filter_accepts_german_date() -> None:
    result = run_report(
        definition(filters=(ReportFilter("booking_date", FilterOperator.LESS, "03.05.2026"),)),
        ROWS,
    )

    assert result.row_count == 2


def test_empty_amount_counts_as_zero_in_comparisons() -> None:
    result = run_report(
        definition(filters=(ReportFilter("debit", FilterOperator.EQUALS, "0"),)), ROWS
    )

    assert result.row_count == 1


def test_grouping_with_subtotals_and_details() -> None:
    result = run_report(
        definition(
            groups=(ReportGroup("cost_center"),),
            sort=ReportSort("booking_date"),
        ),
        ROWS,
    )

    styles = [row.style for row in result.rows]
    assert styles == [
        RowStyle.GROUP,
        RowStyle.NORMAL,
        RowStyle.NORMAL,
        RowStyle.NORMAL,
        RowStyle.SUBTOTAL,
        RowStyle.GROUP,
        RowStyle.NORMAL,
        RowStyle.SUBTOTAL,
    ]
    assert result.rows[0].cells[1] == "Kostenstelle: 100 Lebensmittel"
    assert result.rows[4].cells == ("", "Summe 100 Lebensmittel", "15,00 €", "2,50 €")
    assert result.rows[7].cells[1:] == ("Summe 200 Reisen", "30,00 €", "0,00 €")


def test_summary_only_group_hides_detail_rows() -> None:
    result = run_report(definition(groups=(ReportGroup("cost_center", summary_only=True),)), ROWS)

    assert [row.style for row in result.rows] == [RowStyle.SUBTOTAL, RowStyle.SUBTOTAL]
    assert texts(result, 1) == ["Summe 100 Lebensmittel", "Summe 200 Reisen"]
    assert result.total_row.cells[2] == "45,00 €"


def test_nested_groups_have_a_subtotal_per_level() -> None:
    result = run_report(
        definition(
            groups=(ReportGroup("cost_center"), ReportGroup("booking_date", summary_only=True))
        ),
        ROWS,
    )

    kinds = [row.style for row in result.rows]
    assert kinds.count(RowStyle.GROUP) == 2
    assert kinds.count(RowStyle.SUBTOTAL) == 4 + 2


PLAN_ROWS = [
    {"cost_center": "100", "month": 1, "plan": 1000, "budget": 12000, "remaining_budget": 11000},
    {"cost_center": "100", "month": 2, "plan": 1000, "budget": 12000, "remaining_budget": 9500},
]
PLAN_COLUMNS = ("cost_center", "month", "plan", "budget", "remaining_budget")


def test_non_additive_amounts_show_last_value_in_group_and_nothing_in_total() -> None:
    result = run_report(
        ReportDefinition(
            "Plan",
            ReportSource.PLAN_ACTUAL,
            PLAN_COLUMNS,
            sort=ReportSort("month"),
            groups=(ReportGroup("cost_center"),),
        ),
        PLAN_ROWS,
    )

    subtotal = result.rows[-1]
    assert subtotal.style is RowStyle.SUBTOTAL
    assert subtotal.cells == ("Summe 100", "", "20,00 €", "120,00 €", "95,00 €")
    assert result.total_row.cells == ("Gesamt", "", "20,00 €", "", "")


def test_pdf_table_carries_total_row_and_alignment() -> None:
    result = run_report(
        definition(filters=(ReportFilter("debit", FilterOperator.GREATER, "0"),)), ROWS
    )

    table = result.to_pdf_table()

    assert table.total_row == result.total_row
    assert [column.align_right for column in table.columns] == [False, False, True, True]
    assert any("Filter:" in line for line in table.subtitle_lines)
    assert table.subtitle_lines[-1] == "3 Zeilen"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"columns": ()}, "mindestens eine Spalte"),
        ({"columns": ("debit", "debit")}, "nur einmal"),
        ({"columns": ("gibt_es_nicht",)}, "gehört nicht zur Datenquelle"),
        ({"sort": ReportSort("merchant")}, "muss in der Spaltenauswahl"),
        ({"groups": (ReportGroup("debit"),)}, "nicht gruppiert"),
        ({"groups": (ReportGroup("account"),)}, "muss in der Spaltenauswahl"),
        (
            {"filters": (ReportFilter("debit", FilterOperator.CONTAINS, "1"),)},
            "Operator passt nicht",
        ),
        (
            {"filters": (ReportFilter("debit", FilterOperator.EQUALS, "abc"),)},
            "Betrag ist ungültig",
        ),
        (
            {"filters": (ReportFilter("booking_date", FilterOperator.EQUALS, "31.02.2026"),)},
            "muss ein Datum sein",
        ),
        (
            {"filters": (ReportFilter("debit", FilterOperator.EQUALS, ""),)},
            "fehlt der Vergleichswert",
        ),
    ],
)
def test_invalid_definitions_are_rejected(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        validate_definition(definition(**changes))


def test_at_most_three_group_levels() -> None:
    groups = (
        ReportGroup("cost_center"),
        ReportGroup("booking_date"),
        ReportGroup("merchant"),
    )
    validate_definition(definition(columns=(*COLUMNS, "merchant"), groups=groups))

    with pytest.raises(ValidationError, match="höchstens 3 Gruppenebenen"):
        validate_definition(
            definition(
                columns=(*COLUMNS, "merchant", "status"),
                groups=(*groups, ReportGroup("status")),
            )
        )
