import json
from datetime import date

import pytest
from sqlalchemy import select

from conftest import World
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.application.services.planning_service import (
    MonthPlanInput,
    PlanningService,
)
from meine_kasse.domain.enums import BookingType, ObjectKind, PlanMode, Side
from meine_kasse.domain.errors import (
    BudgetExceededError,
    NotFoundError,
    PeriodError,
    ValidationError,
)
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.infrastructure.database.models import AuditLogModel, PeriodClosureModel
from meine_kasse.infrastructure.database.session import Database

YEAR = 2026
D = date(2026, 5, 10)


def months(**plans: int) -> list[MonthPlanInput]:
    """`m03=1000` -> Plan 10,00 € im März."""
    return [MonthPlanInput(int(key[1:]), cents) for key, cents in plans.items()]


def save(
    planning: PlanningService,
    world: World,
    cost_center: str | None = None,
    *,
    base: int = 10000,
    plans: list[MonthPlanInput] | None = None,
    carry_in: int | None = None,
) -> None:
    planning.save_plan(
        cost_center or world.cc_a,
        YEAR,
        base_budget_cents=base,
        reserve_carry_in_cents=carry_in,
        months=plans or [],
        actor_id=world.actor,
    )


def close_month(database: Database, world: World, month: int) -> None:
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


def audit_entries(database: Database, name: str = "PLAN_UPDATED") -> list[AuditLogModel]:
    with database.session_factory() as session:
        return list(session.scalars(select(AuditLogModel).where(AuditLogModel.name == name)))


def test_empty_plan_view_has_twelve_open_months(planning: PlanningService, world: World) -> None:
    view = planning.get_plan_view(world.cc_a, YEAR)

    assert [m.month for m in view.months] == list(range(1, 13))
    assert view.effective_budget_cents == 0
    assert view.distributed_cents == 0
    assert view.base_editable is True
    assert all(not m.is_closed for m in view.months)


def test_only_standard_cost_centers_can_be_planned(
    planning: PlanningService, master_data: MasterDataService, world: World
) -> None:
    assert [c.number for c in planning.list_planned_cost_centers()] == ["100", "200"]
    master_data.set_cost_center_active(world.cc_b, False)
    assert [c.number for c in planning.list_planned_cost_centers()] == ["100"]
    with pytest.raises(ValidationError, match="ohne Plan"):
        planning.get_plan_view(world.cc_free, YEAR)
    with pytest.raises(ValidationError, match="ohne Plan"):
        save(planning, world, world.cc_free)
    with pytest.raises(NotFoundError):
        planning.get_plan_view("unbekannt", YEAR)


def test_save_stores_budget_months_and_carry_over(
    planning: PlanningService, database: Database, world: World
) -> None:
    plans = [
        MonthPlanInput(1, 2000, 500, PlanMode.QUARTERLY),
        MonthPlanInput(2, 0),
        MonthPlanInput(3, 3000, 0, PlanMode.IRREGULAR),
    ]
    save(planning, world, base=10000, plans=plans, carry_in=700)

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.base_budget_cents == 10000
    # Der Vortrag ins Folgejahr wird berechnet: Vortrag + alle Zuführungen (nichts ausgegeben)
    assert (view.reserve_carry_in_cents, view.reserve_carry_out_cents) == (700, 700 + 10000)
    assert view.distributed_cents == 5000
    assert view.undistributed_cents == 5000
    first, second, third = view.months[:3]
    assert (first.plan_cents, first.reserve_plan_cents, first.plan_mode) == (
        2000,
        500,
        PlanMode.QUARTERLY,
    )
    assert first.reserve_is_manual and third.reserve_is_manual and not second.reserve_is_manual
    assert second.plan_cents == 0 and second.plan_mode is PlanMode.MONTHLY
    assert third.plan_mode is PlanMode.IRREGULAR
    (entry,) = audit_entries(database)
    new_values = json.loads(entry.new_value or "{}")
    assert new_values["base_budget"] == "100,00 €"
    assert new_values["m01_plan"] == "20,00 €"


def test_saving_without_changes_writes_no_second_audit_entry(
    planning: PlanningService, database: Database, world: World
) -> None:
    save(planning, world, plans=months(m01=1000))
    save(planning, world, plans=months(m01=1000))
    assert len(audit_entries(database)) == 1
    save(planning, world, plans=months(m01=1500))
    assert len(audit_entries(database)) == 2


def test_distribution_above_budget_is_rejected_and_nothing_is_saved(
    planning: PlanningService, database: Database, world: World
) -> None:
    save(planning, world, plans=months(m01=4000))

    with pytest.raises(ValidationError, match="übersteigt den Jahresansatz"):
        save(planning, world, plans=months(m01=4000, m02=4000, m03=2001))

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.distributed_cents == 4000
    assert len(audit_entries(database)) == 1


def test_monthly_plan_may_use_the_whole_budget(planning: PlanningService, world: World) -> None:
    save(planning, world, plans=months(m01=5000, m06=5000))
    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.undistributed_cents == 0


@pytest.mark.parametrize(
    "bad",
    [
        [MonthPlanInput(1, -1)],
        [MonthPlanInput(13, 1)],
        [MonthPlanInput(1, 1), MonthPlanInput(1, 2)],
        [MonthPlanInput(1, 1, -5)],
    ],
)
def test_invalid_month_inputs_are_rejected(
    planning: PlanningService, world: World, bad: list[MonthPlanInput]
) -> None:
    with pytest.raises(ValidationError):
        save(planning, world, plans=bad)


def test_negative_budget_or_carry_is_rejected(planning: PlanningService, world: World) -> None:
    with pytest.raises(ValidationError):
        save(planning, world, base=-1)
    with pytest.raises(ValidationError):
        save(planning, world, carry_in=-1)


def test_base_budget_is_fixed_when_planning_is_active(
    planning: PlanningService, booking_control: BookingControlService, world: World
) -> None:
    save(planning, world, base=10000, plans=months(m01=1000))
    booking_control.update(planning_enabled=True, current_year=YEAR, current_month=5)

    with pytest.raises(ValidationError, match="Ansatzumbuchung"):
        save(planning, world, base=12000, plans=months(m01=1000))
    save(planning, world, base=10000, plans=months(m01=3000, m02=2000))

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.base_editable is False
    assert view.distributed_cents == 5000
    with pytest.raises(ValidationError, match="Ansatzumbuchung"):
        save(planning, world, cost_center=world.cc_b, base=100)
    save(planning, world, cost_center=world.cc_b, base=0)


def test_distribution_is_limited_by_the_effective_budget_after_transfers(
    planning: PlanningService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    save(planning, world, world.cc_a, base=10000)
    save(planning, world, world.cc_b, base=0)
    booking_control.update(planning_enabled=True, current_year=YEAR, current_month=5)
    bookings.post(
        booking_type=BookingType.BUDGET_TRANSFER,
        entry_side=Side.DEBIT,
        amount_cents=3000,
        booking_date=D,
        origin_date=D,
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.COST_CENTER, world.cc_b),
        actor_id=world.actor,
    )

    assert planning.get_plan_view(world.cc_a, YEAR).effective_budget_cents == 7000
    assert planning.get_plan_view(world.cc_b, YEAR).effective_budget_cents == 3000
    save(planning, world, world.cc_a, base=10000, plans=months(m01=7000))
    with pytest.raises(ValidationError, match="übersteigt"):
        save(planning, world, world.cc_a, base=10000, plans=months(m01=7001))
    save(planning, world, world.cc_b, base=0, plans=months(m06=3000))


def test_closed_month_cannot_be_changed_but_may_be_resaved_unchanged(
    planning: PlanningService, database: Database, world: World
) -> None:
    save(planning, world, plans=months(m03=1000, m06=1000))
    close_month(database, world, 3)

    save(planning, world, plans=months(m03=1000, m06=2000))
    with pytest.raises(PeriodError, match="03/2026"):
        save(planning, world, plans=months(m03=1500, m06=2000))
    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.months[2].is_closed and not view.months[5].is_closed
    assert view.months[2].plan_cents == 1000
    assert view.months[5].plan_cents == 2000


def test_closed_year_cannot_be_planned(
    planning: PlanningService, database: Database, world: World
) -> None:
    from meine_kasse.infrastructure.database.models import YearClosureModel

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
    with pytest.raises(PeriodError, match="abgeschlossen"):
        save(planning, world)
    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.year_closed and view.base_editable is False
    assert all(month.is_closed for month in view.months)


def test_plan_view_compares_plan_with_actuals(
    planning: PlanningService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    save(planning, world, base=100000, plans=months(m05=20000))
    for side, amount in ((Side.DEBIT, 15000), (Side.CREDIT, 2500), (Side.DEBIT, -500)):
        bookings.post(
            booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
            entry_side=side,
            amount_cents=amount,
            booking_date=D,
            origin_date=D,
            leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
            second=Stelle(ObjectKind.ACCOUNT, world.giro),
            actor_id=world.actor,
        )

    view = planning.get_plan_view(world.cc_a, YEAR)
    may = view.months[4]

    assert (may.debit_cents, may.credit_cents) == (14500, 2500)
    assert may.movement_cents == 12000
    assert may.deviation_cents == 8000
    assert view.movement_cents == 12000
    assert view.remaining_cents == 88000


def test_saved_budget_makes_the_budget_block_usable(
    planning: PlanningService,
    booking_control: BookingControlService,
    bookings: BookingService,
    world: World,
) -> None:
    save(planning, world, base=10000)
    booking_control.update(planning_enabled=True, current_year=YEAR, current_month=5)

    def spend(cents: int) -> None:
        bookings.post(
            booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
            entry_side=Side.DEBIT,
            amount_cents=cents,
            booking_date=D,
            origin_date=D,
            leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
            second=Stelle(ObjectKind.ACCOUNT, world.giro),
            actor_id=world.actor,
        )

    spend(10000)
    with pytest.raises(BudgetExceededError):
        spend(1)
