import json
from datetime import date

import pytest
from sqlalchemy import select

from conftest import World
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.income_planning import IncomeMonthInput
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.application.services.planning_service import PlanningService
from meine_kasse.domain.enums import BookingType, CostCenterKind, IncomeMode, ObjectKind, Side
from meine_kasse.domain.errors import BudgetExceededError, PeriodError, ValidationError
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.infrastructure.database.models import (
    AuditLogModel,
    CostCenterPlanModel,
    PeriodClosureModel,
)
from meine_kasse.infrastructure.database.session import Database

YEAR = 2026
D = date(2026, 5, 10)


def cc(entity_id: str) -> Stelle:
    return Stelle(ObjectKind.COST_CENTER, entity_id)


@pytest.fixture
def rente(master_data: MasterDataService) -> str:
    return master_data.create_cost_center(
        number="900",
        name="Rente",
        valid_from=date(2026, 1, 1),
        kind=CostCenterKind.INCOME,
        income_mode=IncomeMode.PLAN,
    )


@pytest.fixture
def zinsen(master_data: MasterDataService) -> str:
    return master_data.create_cost_center(
        number="910",
        name="Zinsen",
        valid_from=date(2026, 1, 1),
        kind=CostCenterKind.INCOME,
        income_mode=IncomeMode.ACTUAL,
    )


def plan_income(planning: PlanningService, world: World, cost_center: str, **plans: int) -> None:
    """`m01=100000` -> erwartete Einnahme 1.000,00 € im Januar."""
    planning.save_income_plan(
        cost_center,
        YEAR,
        months=[IncomeMonthInput(int(key[1:]), cents) for key, cents in plans.items()],
        actor_id=world.actor,
    )


def book_income(
    bookings: BookingService,
    world: World,
    cost_center: str,
    amount: int,
    *,
    side: Side = Side.CREDIT,
    booking_date: date = D,
) -> str:
    return bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=side,
        amount_cents=amount,
        booking_date=booking_date,
        origin_date=booking_date,
        leading=cc(cost_center),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        booking_text="Eingang",
        actor_id=world.actor,
    )


def pass_on(
    bookings: BookingService,
    world: World,
    source: str,
    target: str,
    amount: int,
    *,
    side: Side = Side.DEBIT,
) -> str:
    return bookings.post(
        booking_type=BookingType.BUDGET_TRANSFER,
        entry_side=side,
        amount_cents=amount,
        booking_date=D,
        origin_date=D,
        leading=cc(source),
        second=cc(target),
        booking_text="Weitergabe",
        actor_id=world.actor,
    )


def enable_planning(booking_control: BookingControlService) -> None:
    booking_control.update(planning_enabled=True, current_year=YEAR, current_month=5)


def test_income_cost_center_stores_its_mode(master_data: MasterDataService, rente: str) -> None:
    created = master_data.get_cost_center(rente)

    assert created.kind is CostCenterKind.INCOME
    assert created.income_mode is IncomeMode.PLAN


def test_income_mode_defaults_to_plan_and_is_only_valid_for_income(
    master_data: MasterDataService,
) -> None:
    default = master_data.create_cost_center(
        number="920", name="Orgel", valid_from=D, kind=CostCenterKind.INCOME
    )

    assert master_data.get_cost_center(default).income_mode is IncomeMode.PLAN
    with pytest.raises(ValidationError, match="Einnahmemodus"):
        master_data.create_cost_center(
            number="921", name="X", valid_from=D, income_mode=IncomeMode.ACTUAL
        )


def test_income_cost_centers_are_not_planned_as_standard(
    planning: PlanningService, world: World, rente: str, zinsen: str
) -> None:
    assert [c.number for c in planning.list_planned_cost_centers()] == ["100", "200"]
    assert [c.number for c in planning.list_income_cost_centers()] == ["900", "910"]
    with pytest.raises(ValidationError, match="Einnahmenplanung"):
        planning.get_plan_view(rente, YEAR)
    with pytest.raises(ValidationError, match="keine Einnahmen-Kostenstelle"):
        planning.get_income_view(world.cc_a, YEAR)


def test_income_plan_is_compared_with_booked_income(
    planning: PlanningService, bookings: BookingService, world: World, rente: str
) -> None:
    plan_income(planning, world, rente, m05=100000, m06=100000)
    book_income(bookings, world, rente, 90000)

    view = planning.get_income_view(rente, YEAR)

    may = view.months[4]
    assert (may.plan_cents, may.realized_cents, may.deviation_cents) == (100000, 90000, -10000)
    assert view.planned_cents == 200000
    assert view.realized_cents == 90000
    assert view.open_expected_cents == 110000
    assert view.available_cents == 200000 and view.free_cents == 200000


def test_booked_income_can_exceed_the_plan(
    planning: PlanningService, bookings: BookingService, world: World, zinsen: str
) -> None:
    book_income(bookings, world, zinsen, 2500)

    view = planning.get_income_view(zinsen, YEAR)

    assert view.planned_cents == 0
    assert view.months[4].deviation_cents == 2500
    assert view.open_expected_cents == 0


def test_saving_income_plan_is_audited_and_unchanged_save_is_not(
    planning: PlanningService, database: Database, world: World, rente: str
) -> None:
    plan_income(planning, world, rente, m01=5000)
    plan_income(planning, world, rente, m01=5000)
    plan_income(planning, world, rente, m01=7000)

    with database.session_factory() as session:
        entries = list(
            session.scalars(
                select(AuditLogModel).where(AuditLogModel.name == "INCOME_PLAN_UPDATED")
            )
        )
    assert len(entries) == 2
    assert json.loads(entries[1].old_value or "{}") == {"m01_plan": "50,00 €"}
    assert json.loads(entries[1].new_value or "{}") == {"m01_plan": "70,00 €"}


def test_income_plan_rejects_negative_amounts_and_closed_months(
    planning: PlanningService, database: Database, world: World, rente: str
) -> None:
    plan_income(planning, world, rente, m01=5000)
    with pytest.raises(ValidationError):
        plan_income(planning, world, rente, m02=-1)
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

    with pytest.raises(PeriodError, match="abgeschlossen"):
        plan_income(planning, world, rente, m01=6000)
    plan_income(planning, world, rente, m01=5000, m02=100)


def test_income_can_be_booked_without_plan_while_planning_is_active(
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    zinsen: str,
) -> None:
    enable_planning(booking_control)

    book_income(bookings, world, zinsen, 1234)

    assert planning.get_income_view(zinsen, YEAR).realized_cents == 1234


def test_plan_mode_passes_on_the_planned_income(
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    database: Database,
    world: World,
    rente: str,
) -> None:
    enable_planning(booking_control)
    plan_income(planning, world, rente, m01=100000, m02=100000)

    pass_on(bookings, world, rente, world.cc_a, 150000)

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.effective_budget_cents == 150000
    income = planning.get_income_view(rente, YEAR)
    assert income.passed_on_cents == 150000 and income.free_cents == 50000
    with database.session_factory() as session:
        stored = session.scalars(
            select(CostCenterPlanModel).where(CostCenterPlanModel.cost_center_id == rente)
        ).one()
        assert stored.budget_transfer_cents == -150000
    with pytest.raises(BudgetExceededError, match="höchstens 500,00 €"):
        pass_on(bookings, world, rente, world.cc_a, 50001)
    pass_on(bookings, world, rente, world.cc_a, 50000)


def test_plan_mode_allows_passing_on_booked_income_above_plan(
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    rente: str,
) -> None:
    enable_planning(booking_control)
    plan_income(planning, world, rente, m01=10000)
    book_income(bookings, world, rente, 25000)

    pass_on(bookings, world, rente, world.cc_a, 25000)

    assert planning.get_income_view(rente, YEAR).free_cents == 0


def test_actual_mode_passes_on_only_booked_income(
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    zinsen: str,
) -> None:
    enable_planning(booking_control)
    plan_income(planning, world, zinsen, m12=50000)

    with pytest.raises(BudgetExceededError, match="höchstens 0,00 €"):
        pass_on(bookings, world, zinsen, world.cc_a, 1)
    book_income(bookings, world, zinsen, 3000)
    pass_on(bookings, world, zinsen, world.cc_a, 3000)

    view = planning.get_income_view(zinsen, YEAR)
    assert view.available_cents == 3000 and view.free_cents == 0
    assert (
        view.open_expected_cents == 50000
    )  # Einnahme im Mai ersetzt nicht die im Dezember erwartete
    with pytest.raises(BudgetExceededError):
        pass_on(bookings, world, zinsen, world.cc_a, 1)


def test_income_cost_center_cannot_receive_budget(
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
    rente: str,
) -> None:
    enable_planning(booking_control)

    with pytest.raises(ValidationError, match="nicht erhalten"):
        pass_on(bookings, world, world.cc_a, rente, 100)
    with pytest.raises(ValidationError, match="nicht erhalten"):
        pass_on(bookings, world, rente, world.cc_a, 100, side=Side.CREDIT)


def test_income_transfer_needs_planning_and_a_standard_receiver(
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    rente: str,
    zinsen: str,
) -> None:
    plan_income(planning, world, rente, m01=1000)
    with pytest.raises(ValidationError, match="aktivierter Planung"):
        pass_on(bookings, world, rente, world.cc_a, 100)

    enable_planning(booking_control)
    with pytest.raises(ValidationError, match="nicht erhalten"):
        pass_on(bookings, world, rente, zinsen, 100)
    with pytest.raises(ValidationError, match="Planung"):
        pass_on(bookings, world, rente, world.cc_free, 100)


def test_income_cannot_drop_below_the_passed_on_amount(
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    zinsen: str,
) -> None:
    enable_planning(booking_control)
    income = book_income(bookings, world, zinsen, 10000)
    pass_on(bookings, world, zinsen, world.cc_a, 6000)

    with pytest.raises(BudgetExceededError, match="bereits 60,00 € .* umgebucht"):
        bookings.reverse(income, booking_date=D, actor_id=world.actor)
    with pytest.raises(BudgetExceededError):
        bookings.delete(income, actor_id=world.actor)
    book_income(bookings, world, zinsen, 3000, side=Side.DEBIT)
    with pytest.raises(BudgetExceededError):
        book_income(bookings, world, zinsen, 1001, side=Side.DEBIT)

    assert planning.get_income_view(zinsen, YEAR).realized_cents == 7000


def test_income_plan_cannot_drop_below_the_passed_on_amount(
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    rente: str,
) -> None:
    enable_planning(booking_control)
    plan_income(planning, world, rente, m01=10000, m02=10000)
    pass_on(bookings, world, rente, world.cc_a, 15000)

    with pytest.raises(BudgetExceededError, match="Plan kann nicht"):
        plan_income(planning, world, rente, m01=10000, m02=4999)
    plan_income(planning, world, rente, m01=10000, m02=5000)
    plan_income(planning, world, rente, m01=10000, m02=15000)


def test_reversing_a_pass_on_frees_the_income_again(
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    zinsen: str,
) -> None:
    enable_planning(booking_control)
    book_income(bookings, world, zinsen, 5000)
    transfer = pass_on(bookings, world, zinsen, world.cc_a, 5000)

    bookings.reverse(transfer, booking_date=D, actor_id=world.actor)

    assert planning.get_income_view(zinsen, YEAR).passed_on_cents == 0
    assert planning.get_plan_view(world.cc_a, YEAR).effective_budget_cents == 0


def test_passed_on_amount_cannot_be_withdrawn_from_a_spent_cost_center(
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
    zinsen: str,
) -> None:
    enable_planning(booking_control)
    book_income(bookings, world, zinsen, 5000)
    transfer = pass_on(bookings, world, zinsen, world.cc_a, 5000)
    bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=Side.DEBIT,
        amount_cents=4000,
        booking_date=D,
        origin_date=D,
        leading=cc(world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        actor_id=world.actor,
    )

    with pytest.raises(BudgetExceededError):
        bookings.reverse(transfer, booking_date=D, actor_id=world.actor)


def test_rebuild_projections_keeps_income_state(
    booking_control: BookingControlService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    rente: str,
) -> None:
    enable_planning(booking_control)
    plan_income(planning, world, rente, m01=10000)
    book_income(bookings, world, rente, 4000)
    pass_on(bookings, world, rente, world.cc_a, 8000)

    bookings.rebuild_projections(actor_id=world.actor)

    view = planning.get_income_view(rente, YEAR)
    assert (view.realized_cents, view.passed_on_cents, view.planned_cents) == (4000, 8000, 10000)
    assert planning.get_plan_view(world.cc_a, YEAR).effective_budget_cents == 8000


def test_cost_center_info_describes_income(
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    rente: str,
) -> None:
    plan_income(planning, world, rente, m05=10000)
    book_income(bookings, world, rente, 4000)

    info = bookings.cost_center_info(rente, D)

    assert info.income_mode is IncomeMode.PLAN
    assert (info.income_planned_cents, info.income_realized_cents) == (10000, 4000)
    assert info.income_free_cents == 10000
    assert info.planning_active is False


def test_migration_to_income_keeps_existing_cost_centers_and_their_data(
    database: Database,
    master_data: MasterDataService,
    bookings: BookingService,
    planning: PlanningService,
    world: World,
    rente: str,
) -> None:
    from sqlalchemy import text

    from meine_kasse.infrastructure.database.migrate import downgrade_database, upgrade_database

    plan_income(planning, world, rente, m05=10000)
    book_income(bookings, world, world.cc_a, 2500)
    downgrade_database(database.engine, "0006")
    upgrade_database(database.engine)

    assert master_data.get_cost_center(world.cc_a).kind is CostCenterKind.STANDARD
    assert master_data.get_cost_center(world.cc_free).kind is CostCenterKind.WITHOUT_PLAN
    downgraded = master_data.get_cost_center(rente)
    assert (downgraded.kind, downgraded.income_mode) == (CostCenterKind.WITHOUT_PLAN, None)
    assert planning.get_plan_view(world.cc_a, YEAR).months[4].credit_cents == 2500
    with database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
    created = master_data.create_cost_center(
        number="930", name="Neu", valid_from=D, kind=CostCenterKind.INCOME
    )
    assert master_data.get_cost_center(created).income_mode is IncomeMode.PLAN
