from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from conftest import TODAY, World
from meine_kasse.application.reporting.pdf_model import RowStyle
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.document_service import DocumentService
from meine_kasse.application.services.income_planning import IncomeMonthInput
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.application.services.planning_service import MonthPlanInput, PlanningService
from meine_kasse.application.services.report_service import ReportService
from meine_kasse.domain.entities import ReportDefinition, ReportFilter, ReportGroup, ReportSort
from meine_kasse.domain.enums import (
    BookingType,
    CostCenterKind,
    DocumentType,
    FilterOperator,
    IncomeMode,
    ObjectKind,
    ReportSource,
    Side,
)
from meine_kasse.domain.errors import NotFoundError, ValidationError
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.infrastructure.reporting.pdf_renderer import ReportlabPdfRenderer

D = date(2026, 5, 10)
YEAR = 2026


@pytest.fixture
def reports(
    uow_factory: Callable[[], UnitOfWork], planning: PlanningService, tmp_path: Path
) -> ReportService:
    documents = DocumentService(uow_factory, ReportlabPdfRenderer(), tmp_path / "Dokumente")
    return ReportService(uow_factory, planning, documents, today=lambda: TODAY)


def book(
    bookings: BookingService,
    world: World,
    *,
    side: Side = Side.DEBIT,
    amount: int,
    cost_center: str | None = None,
    account: str | None = None,
    text: str = "Einkauf",
    booking_date: date = D,
) -> str:
    return bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=side,
        amount_cents=amount,
        booking_date=booking_date,
        origin_date=booking_date,
        leading=Stelle(ObjectKind.COST_CENTER, cost_center or world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, account or world.giro),
        merchant="Markt",
        booking_text=text,
        actor_id=world.actor,
    )


def booking_definition(**changes: object) -> ReportDefinition:
    values: dict[str, object] = {
        "name": "Buchungen",
        "data_source": ReportSource.BOOKINGS,
        "columns": ("booking_date", "cost_center", "account", "debit", "credit", "status"),
    }
    values.update(changes)
    return ReportDefinition(**values)  # type: ignore[arg-type]


def test_bookings_source_keeps_signs_and_sides(
    reports: ReportService, bookings: BookingService, world: World
) -> None:
    book(bookings, world, amount=5000)
    book(bookings, world, side=Side.CREDIT, amount=2000, text="Erstattung")
    book(bookings, world, amount=-300, text="Korrektur")

    result = reports.run(booking_definition(sort=ReportSort("debit")))

    assert result.row_count == 3
    assert result.total_row.cells[3:5] == ("47,00 €", "20,00 €")
    cells = {tuple(row.cells[3:5]) for row in result.rows}
    assert cells == {("50,00 €", ""), ("", "20,00 €"), ("-3,00 €", "")}
    assert all(row.cells[1] == "100 Lebensmittel" for row in result.rows)
    assert all(row.cells[2] == "1000 Girokonto" for row in result.rows)


def test_bookings_can_be_filtered_and_grouped(
    reports: ReportService, bookings: BookingService, world: World
) -> None:
    book(bookings, world, amount=1000)
    book(bookings, world, amount=2000, cost_center=world.cc_b)
    book(bookings, world, amount=4000, cost_center=world.cc_b)

    result = reports.run(
        booking_definition(
            filters=(ReportFilter("debit", FilterOperator.GREATER, "15,00"),),
            groups=(ReportGroup("cost_center", summary_only=True),),
        )
    )

    assert [row.cells[1] for row in result.rows] == ["Summe 200 Reisen"]
    assert result.rows[0].cells[3] == "60,00 €"
    assert result.total_row.cells[3] == "60,00 €"


def test_reversal_and_reversed_booking_are_marked(
    reports: ReportService, bookings: BookingService, world: World
) -> None:
    original = book(bookings, world, amount=1000)
    bookings.reverse(original, booking_date=D, actor_id=world.actor)

    result = reports.run(booking_definition(sort=ReportSort("booking_date")))

    status = sorted(row.cells[5] for row in result.rows)
    assert status == ["offen, Storno", "offen, storniert"]
    assert result.total_row.cells[3] == "0,00 €"


def test_accounts_source_lists_opening_balance_and_balance(
    reports: ReportService, bookings: BookingService, world: World
) -> None:
    book(bookings, world, amount=5000)
    book(bookings, world, side=Side.CREDIT, amount=1500)

    result = reports.run(
        ReportDefinition(
            "Konten",
            ReportSource.ACCOUNTS,
            ("account", "account_type", "opening_balance", "debit", "credit", "balance"),
            sort=ReportSort("account"),
        )
    )

    giro, savings = result.rows
    assert giro.cells == ("1000 Girokonto", "Giro", "0,00 €", "50,00 €", "15,00 €", "-35,00 €")
    assert savings.cells[3:] == ("0,00 €", "0,00 €", "0,00 €")
    assert result.total_row.cells[3:] == ("50,00 €", "15,00 €", "")


def test_plan_actual_source_reports_budget_remaining_and_deviation(
    reports: ReportService,
    planning: PlanningService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=12000,
        reserve_carry_in_cents=None,
        months=[MonthPlanInput(5, 3000), MonthPlanInput(6, 3000)],
        actor_id=world.actor,
    )
    book(bookings, world, amount=2000)
    book(bookings, world, amount=-500, text="Rückgabe")

    result = reports.run(
        ReportDefinition(
            "Plan/Ist",
            ReportSource.PLAN_ACTUAL,
            ("cost_center", "month", "debit", "movement", "plan", "deviation", "budget"),
            filters=(
                ReportFilter("month", FilterOperator.GREATER_OR_EQUAL, "5"),
                ReportFilter("month", FilterOperator.LESS_OR_EQUAL, "6"),
            ),
            sort=ReportSort("month"),
        )
    )

    may, june = result.rows
    assert may.cells == (
        "100 Lebensmittel",
        "5",
        "15,00 €",
        "15,00 €",
        "30,00 €",
        "15,00 €",
        "120,00 €",
    )
    assert june.cells[1] == "6"
    assert june.cells[4:] == ("30,00 €", "30,00 €", "120,00 €")
    assert result.total_row.cells[2:] == ("15,00 €", "15,00 €", "60,00 €", "45,00 €", "")


def test_plan_actual_remaining_budget_is_cumulative(
    reports: ReportService, planning: PlanningService, bookings: BookingService, world: World
) -> None:
    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=12000,
        reserve_carry_in_cents=None,
        months=[MonthPlanInput(5, 3000), MonthPlanInput(6, 3000)],
        actor_id=world.actor,
    )
    book(bookings, world, amount=2000)

    result = reports.run(
        ReportDefinition(
            "Restansatz",
            ReportSource.PLAN_ACTUAL,
            ("cost_center", "month", "remaining_budget"),
            sort=ReportSort("month"),
            groups=(ReportGroup("cost_center", summary_only=True),),
        )
    )

    assert result.rows[0].style is RowStyle.SUBTOTAL
    assert result.rows[0].cells[2] == "100,00 €"


def test_cost_centers_without_plan_are_not_part_of_plan_actual(
    reports: ReportService, bookings: BookingService, world: World
) -> None:
    book(bookings, world, amount=1000, cost_center=world.cc_free)

    result = reports.run(
        ReportDefinition("Plan/Ist", ReportSource.PLAN_ACTUAL, ("cost_center", "month", "debit"))
    )

    assert result.row_count == 0


def test_flagged_cost_center_without_plan_shows_its_expenses(
    reports: ReportService,
    bookings: BookingService,
    master_data: MasterDataService,
    world: World,
) -> None:
    master_data.update_cost_center(
        world.cc_free,
        number="300",
        name="Sonstiges",
        valid_from=date(2026, 1, 1),
        always_in_plan_report=True,
        actor_id=world.actor,
    )
    book(bookings, world, amount=1000, cost_center=world.cc_free)
    book(bookings, world, amount=400, cost_center=world.cc_free, text="Mehr")

    result = reports.run(
        ReportDefinition(
            "Plan/Ist",
            ReportSource.PLAN_ACTUAL,
            ("cost_center", "planning", "month", "debit", "plan", "budget", "remaining_budget"),
        )
    )

    assert [row.cells for row in result.rows] == [
        ("300 Sonstiges", "Ohne Plan", "5", "14,00 €", "0,00 €", "", ""),
        ("300 Sonstiges", "Ohne Plan", "", "0,00 €", "0,00 €", "", ""),
    ]
    assert result.total_row.cells[3:5] == ("14,00 €", "0,00 €")


def test_flagged_cost_center_without_plan_and_booking_is_still_listed(
    reports: ReportService,
    master_data: MasterDataService,
    world: World,
) -> None:
    master_data.update_cost_center(
        world.cc_free,
        number="300",
        name="Sonstiges",
        valid_from=date(2026, 1, 1),
        always_in_plan_report=True,
        actor_id=world.actor,
    )

    result = reports.run(
        ReportDefinition(
            "Plan/Ist",
            ReportSource.PLAN_ACTUAL,
            ("cost_center", "planning", "year", "month", "debit", "plan", "budget"),
        )
    )

    assert [row.cells for row in result.rows] == [
        ("300 Sonstiges", "Ohne Plan", "2026", "", "0,00 €", "0,00 €", ""),
        ("300 Sonstiges", "Ohne Plan", "2027", "", "0,00 €", "0,00 €", ""),
    ]


def test_empty_rows_can_be_excluded_by_row_kind_filter(
    reports: ReportService,
    master_data: MasterDataService,
    world: World,
) -> None:
    master_data.update_cost_center(
        world.cc_free,
        number="300",
        name="Sonstiges",
        valid_from=date(2026, 1, 1),
        always_in_plan_report=True,
        actor_id=world.actor,
    )

    result = reports.run(
        ReportDefinition(
            "Plan/Ist",
            ReportSource.PLAN_ACTUAL,
            ("cost_center", "row_kind", "year"),
            filters=(ReportFilter("row_kind", FilterOperator.NOT_EQUALS, "Ohne Werte"),),
        )
    )

    assert result.row_count == 0


def test_flagged_cost_center_is_not_listed_before_its_valid_from_year(
    reports: ReportService,
    master_data: MasterDataService,
    world: World,
) -> None:
    master_data.update_cost_center(
        world.cc_free,
        number="300",
        name="Sonstiges",
        valid_from=date(2027, 1, 1),
        always_in_plan_report=True,
        actor_id=world.actor,
    )

    result = reports.run(
        ReportDefinition("Plan/Ist", ReportSource.PLAN_ACTUAL, ("cost_center", "year"))
    )

    assert [row.cells for row in result.rows] == [("300 Sonstiges", "2027")]


def test_flagged_planned_cost_center_is_listed_without_plan_and_booking(
    reports: ReportService,
    master_data: MasterDataService,
    world: World,
) -> None:
    master_data.update_cost_center(
        world.cc_b,
        number="200",
        name="Reisen",
        valid_from=date(2026, 1, 1),
        always_in_plan_report=True,
        actor_id=world.actor,
    )

    result = reports.run(
        ReportDefinition(
            "Plan/Ist",
            ReportSource.PLAN_ACTUAL,
            ("cost_center", "planning", "year", "month", "budget", "remaining_budget"),
        )
    )

    assert [row.cells for row in result.rows] == [
        ("200 Reisen", "Mit Plan", "2026", "", "0,00 €", "0,00 €"),
        ("200 Reisen", "Mit Plan", "2027", "", "0,00 €", "0,00 €"),
    ]


def test_flagged_planned_cost_center_shows_years_with_expenses_but_no_plan(
    reports: ReportService,
    bookings: BookingService,
    master_data: MasterDataService,
    world: World,
) -> None:
    master_data.update_cost_center(
        world.cc_b,
        number="200",
        name="Reisen",
        valid_from=date(2026, 1, 1),
        always_in_plan_report=True,
        actor_id=world.actor,
    )
    book(bookings, world, amount=2500, cost_center=world.cc_b)
    book(bookings, world, amount=700)

    result = reports.run(
        ReportDefinition(
            "Plan/Ist",
            ReportSource.PLAN_ACTUAL,
            ("cost_center", "planning", "debit"),
        )
    )

    assert [row.cells for row in result.rows] == [
        ("200 Reisen", "Mit Plan", "25,00 €"),
        ("200 Reisen", "Mit Plan", "0,00 €"),
    ]


def test_plan_report_flag_is_rejected_for_income_cost_centers(
    master_data: MasterDataService,
) -> None:
    with pytest.raises(ValidationError, match="Einnahmen-Kostenstellen"):
        master_data.create_cost_center(
            number="900",
            name="Rente",
            valid_from=date(2026, 1, 1),
            kind=CostCenterKind.INCOME,
            always_in_plan_report=True,
        )


def test_income_source_lists_plan_actual_and_liquidity_per_month(
    reports: ReportService,
    planning: PlanningService,
    bookings: BookingService,
    master_data: MasterDataService,
    world: World,
) -> None:
    rente = master_data.create_cost_center(
        number="900",
        name="Rente",
        valid_from=date(2026, 1, 1),
        kind=CostCenterKind.INCOME,
        income_mode=IncomeMode.PLAN,
    )
    zinsen = master_data.create_cost_center(
        number="910",
        name="Zinsen",
        valid_from=date(2026, 1, 1),
        kind=CostCenterKind.INCOME,
        income_mode=IncomeMode.ACTUAL,
    )
    planning.save_income_plan(
        rente,
        YEAR,
        months=[IncomeMonthInput(5, 100000), IncomeMonthInput(6, 100000)],
        actor_id=world.actor,
    )
    planning.save_income_plan(
        zinsen, YEAR, months=[IncomeMonthInput(5, 5000)], actor_id=world.actor
    )
    book(bookings, world, side=Side.CREDIT, amount=98000, cost_center=rente, text="Mai")

    result = reports.run(
        ReportDefinition(
            "Einnahmen",
            ReportSource.INCOME,
            (
                "cost_center",
                "month",
                "availability",
                "plan",
                "realized",
                "deviation",
                "open_expected",
                "liquidity",
            ),
            sort=ReportSort("month"),
        )
    )

    assert sorted(row.cells for row in result.rows) == [
        (
            "900 Rente",
            "5",
            "Nach Plan",
            "1.000,00 €",
            "980,00 €",
            "-20,00 €",
            "20,00 €",
            "1.000,00 €",
        ),
        (
            "900 Rente",
            "6",
            "Nach Plan",
            "1.000,00 €",
            "0,00 €",
            "-1.000,00 €",
            "1.000,00 €",
            "1.000,00 €",
        ),
        ("910 Zinsen", "5", "Nur nach Ist", "50,00 €", "0,00 €", "-50,00 €", "50,00 €", "0,00 €"),
    ]
    assert result.total_row.cells[3:] == (
        "2.050,00 €",
        "980,00 €",
        "-1.070,00 €",
        "1.070,00 €",
        "2.000,00 €",
    )


def test_income_source_can_be_saved_as_a_definition(reports: ReportService, world: World) -> None:
    reports.save_definition(
        world.actor,
        ReportDefinition("Einnahmen", ReportSource.INCOME, ("cost_center", "plan")),
    )

    saved = reports.list_definitions(world.actor)

    assert [item.data_source for item in saved] == [ReportSource.INCOME]


def test_invalid_definition_is_rejected_by_the_service(reports: ReportService) -> None:
    with pytest.raises(ValidationError, match="mindestens eine Spalte"):
        reports.run(booking_definition(columns=()))


def test_definitions_are_saved_per_user_and_replaced_by_name(
    reports: ReportService, auth, world: World
) -> None:
    other = auth.create_user(
        name="berta", last_name="B", first_name="B", initial_password="Erstpasswort-1"
    )
    first = booking_definition(
        name="  Monatsbericht ",
        filters=(ReportFilter("booking_text", FilterOperator.CONTAINS, "Markt"),),
        sort=ReportSort("debit", ascending=False),
        groups=(ReportGroup("cost_center", summary_only=True),),
        columns=("cost_center", "debit", "credit"),
    )

    reports.save_definition(world.actor, first)
    saved = reports.list_definitions(world.actor)

    assert [item.name for item in saved] == ["Monatsbericht"]
    assert saved[0].filters == first.filters
    assert saved[0].sort == ReportSort("debit", ascending=False)
    assert saved[0].groups == (ReportGroup("cost_center", summary_only=True),)
    assert saved[0].columns == ("cost_center", "debit", "credit")
    assert reports.list_definitions(other) == []

    reports.save_definition(world.actor, booking_definition(name="Monatsbericht"))
    assert len(reports.list_definitions(world.actor)) == 1
    assert reports.list_definitions(world.actor)[0].filters == ()

    reports.save_definition(other, booking_definition(name="Monatsbericht"))
    assert len(reports.list_definitions(other)) == 1


def test_save_requires_a_valid_name_and_definition(reports: ReportService, world: World) -> None:
    with pytest.raises(ValidationError, match="Namen"):
        reports.save_definition(world.actor, booking_definition(name="  "))
    with pytest.raises(ValidationError, match="höchstens 200"):
        reports.save_definition(world.actor, booking_definition(name="x" * 201))
    with pytest.raises(ValidationError, match="mindestens eine Spalte"):
        reports.save_definition(world.actor, booking_definition(columns=()))


def test_delete_definition(reports: ReportService, world: World) -> None:
    reports.save_definition(world.actor, booking_definition(name="Weg damit"))

    reports.delete_definition(world.actor, "Weg damit")

    assert reports.list_definitions(world.actor) == []
    with pytest.raises(NotFoundError):
        reports.delete_definition(world.actor, "Weg damit")


def test_export_pdf_is_archived_as_report(
    reports: ReportService, bookings: BookingService, world: World, tmp_path: Path
) -> None:
    book(bookings, world, amount=1234)

    view = reports.export_pdf(booking_definition(), suffix="Test", actor_id=world.actor)

    assert view.document_type is DocumentType.REPORT
    assert view.file_name.endswith("_Buchungen_Test.pdf")
    assert (tmp_path / "Dokumente" / view.file_name).read_bytes().startswith(b"%PDF-")
