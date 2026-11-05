"""Rückstellungen: Entlastung, Jahresvortrag, Hinweise und Prüfungen (Architekturvorgabe 2.12)."""

from datetime import date

import pytest
from sqlalchemy import select

from conftest import World
from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.application.services.booking_service import BookingService
from meine_kasse.application.services.closing_service import ClosingService
from meine_kasse.application.services.planning_service import MonthPlanInput, PlanningService
from meine_kasse.domain.enums import BookingType, ObjectKind, Side
from meine_kasse.domain.errors import PeriodError, ValidationError
from meine_kasse.domain.services.booking_rules import Stelle
from meine_kasse.infrastructure.database.models import (
    AuditLogModel,
    CostCenterPlanModel,
    MonthlyActualModel,
    MonthlyPlanModel,
)
from meine_kasse.infrastructure.database.session import Database

YEAR = 2026


def _save(
    planning: PlanningService,
    world: World,
    *,
    base: int = 120000,
    year: int = YEAR,
    plans: list[MonthPlanInput] | None = None,
    carry_in: int | None = None,
    cost_center: str | None = None,
) -> None:
    planning.save_plan(
        cost_center or world.cc_a,
        year,
        base_budget_cents=base,
        reserve_carry_in_cents=carry_in,
        months=plans or [],
        actor_id=world.actor,
    )


def _spend(
    bookings: BookingService,
    world: World,
    *,
    origin: date,
    cents: int,
    side: Side = Side.DEBIT,
    booked: date = date(2026, 5, 10),
    cost_center: str | None = None,
) -> str:
    return bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=side,
        amount_cents=cents,
        booking_date=booked,
        origin_date=origin,
        leading=Stelle(ObjectKind.COST_CENTER, cost_center or world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        actor_id=world.actor,
    )


def _release(planning: PlanningService, world: World, year: int = YEAR) -> dict[int, int]:
    view = planning.get_plan_view(world.cc_a, year)
    return {m.month: m.reserve_release_cents for m in view.months if m.reserve_release_cents}


def _stored_actuals(database: Database) -> dict[tuple[int, int], int]:
    with database.session_factory() as session:
        return {
            (row.year, row.month): row.reserve_actual_cents
            for row in session.scalars(select(MonthlyActualModel))
            if row.reserve_actual_cents
        }


# Maschinelle Verteilung beim Speichern


def test_saving_distributes_the_whole_budget_evenly_as_reserve(
    planning: PlanningService, world: World
) -> None:
    _save(planning, world)

    view = planning.get_plan_view(world.cc_a, YEAR)

    assert [m.reserve_plan_cents for m in view.months] == [10000] * 12
    assert not any(m.reserve_is_manual for m in view.months)
    assert view.reserve_carry_out_cents == 120000


def test_planning_every_month_means_no_reserve(planning: PlanningService, world: World) -> None:
    plans = [MonthPlanInput(month, 10000) for month in range(1, 13)]

    _save(planning, world, plans=plans)

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert all(m.reserve_plan_cents == 0 for m in view.months)
    assert view.reserve_carry_out_cents == 0
    assert view.reserve_notices == ()


def test_planned_payments_keep_the_even_reserve_and_relieve_it_in_the_plan(
    planning: PlanningService, world: World
) -> None:
    _save(planning, world, plans=[MonthPlanInput(3, 60000), MonthPlanInput(9, 60000)])

    view = planning.get_plan_view(world.cc_a, YEAR)

    assert [m.reserve_plan_cents for m in view.months] == [10000] * 12
    assert [m.reserve_release_cents for m in view.months if m.reserve_release_cents] == [
        30000,
        60000,
    ]
    assert view.reserve_carry_out_cents == 30000
    assert len(view.reserve_notices) == 1 and "Monat 03/2026" in view.reserve_notices[0]


def test_reserve_for_payment_targets_is_raised_before_planned_payments(
    planning: PlanningService, world: World
) -> None:
    preview = planning.preview_reserve(
        world.cc_a,
        YEAR,
        base_budget_cents=120000,
        carry_in_cents=0,
        months=[MonthPlanInput(3, 60000), MonthPlanInput(9, 60000)],
        to_payment_targets=True,
    )

    reserves = [preview.reserve_plan[m] for m in range(1, 13)]
    assert reserves == [20000] * 3 + [10000] * 6 + [0] * 3
    assert preview.notices == () and preview.carry_out_cents == 0


def test_the_actual_payment_replaces_the_planned_release_after_closing(
    planning: PlanningService,
    bookings: BookingService,
    closing: ClosingService,
    booking_control: BookingControlService,
    world: World,
) -> None:
    booking_control.update(planning_enabled=False, current_year=YEAR, current_month=5)
    _save(planning, world, plans=[MonthPlanInput(5, 30000)])
    assert planning.get_plan_view(world.cc_a, YEAR).reserve_carry_out_cents == 120000 - 30000

    _spend(bookings, world, origin=date(2026, 5, 5), cents=20000)
    assert planning.get_plan_view(world.cc_a, YEAR).reserve_carry_out_cents == 120000 - 30000

    closing.close_month(actor_id=world.actor)

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.reserve_carry_out_cents == 120000 - 20000
    assert _release(planning, world) == {5: 20000}


def test_manual_months_are_kept_when_the_plan_changes(
    planning: PlanningService, world: World
) -> None:
    _save(planning, world, plans=[MonthPlanInput(4, 0, 30000)])
    _save(planning, world, plans=[MonthPlanInput(4, 0, 30000), MonthPlanInput(8, 50000)])

    view = planning.get_plan_view(world.cc_a, YEAR)

    assert view.months[3].reserve_plan_cents == 30000 and view.months[3].reserve_is_manual
    assert sum(m.reserve_plan_cents for m in view.months) == 120000
    assert view.reserve_notices == ()


def test_months_not_mentioned_keep_their_manual_state(
    planning: PlanningService, world: World
) -> None:
    _save(planning, world, plans=[MonthPlanInput(4, 0, 30000)])

    _save(planning, world, plans=[MonthPlanInput(5, 20000)])

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.months[3].reserve_plan_cents == 30000 and view.months[3].reserve_is_manual
    assert view.months[4].plan_cents == 20000


def test_closed_months_keep_their_reserve_while_open_months_are_recalculated(
    planning: PlanningService, database: Database, world: World
) -> None:
    from meine_kasse.infrastructure.database.models import PeriodClosureModel

    _save(planning, world)
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

    _save(planning, world, plans=[MonthPlanInput(7, 60000)])

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.months[0].reserve_plan_cents == 10000
    assert sum(m.reserve_plan_cents for m in view.months) == 120000
    assert view.reserve_notices == ()


def test_manual_reserve_above_the_budget_is_rejected(
    planning: PlanningService, database: Database, world: World
) -> None:
    with pytest.raises(ValidationError, match="Rückstellungen.*übersteigen"):
        _save(planning, world, base=10000, plans=[MonthPlanInput(1, 0, 10001)])

    assert planning.get_plan_view(world.cc_a, YEAR).base_budget_cents == 0


def test_a_shortfall_in_the_plan_is_reported_as_notice(
    planning: PlanningService, world: World
) -> None:
    _save(
        planning,
        world,
        base=60000,
        plans=[MonthPlanInput(1, 10000, 0)],
    )

    view = planning.get_plan_view(world.cc_a, YEAR)

    assert len(view.reserve_notices) == 1
    assert "01/2026" in view.reserve_notices[0] and "100,00 €" in view.reserve_notices[0]


# Vortrag


def test_carry_in_is_manual_without_a_previous_year_plan(
    planning: PlanningService, world: World
) -> None:
    _save(planning, world, carry_in=5000)

    view = planning.get_plan_view(world.cc_a, YEAR)

    assert view.reserve_carry_in_editable
    assert view.reserve_carry_in_cents == 5000
    assert view.reserve_carry_out_cents == 5000 + 120000


def test_carry_in_follows_the_previous_year_until_it_is_overridden_by_hand(
    planning: PlanningService, world: World
) -> None:
    _save(planning, world, year=YEAR - 1, base=60000)

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.reserve_carry_in_cents == 60000
    assert view.reserve_carry_in_editable and not view.reserve_carry_in_manual
    assert view.reserve_carry_in_derivable

    _save(planning, world, base=10000, carry_in=60000)
    assert not planning.get_plan_view(world.cc_a, YEAR).reserve_carry_in_manual

    _save(planning, world, base=10000, carry_in=1000)
    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.reserve_carry_in_cents == 1000 and view.reserve_carry_in_manual
    assert view.reserve_carry_out_cents == 1000 + 10000

    _save(planning, world, year=YEAR - 1, base=70000)  # Eine Überschreibung bleibt bestehen.
    assert planning.get_plan_view(world.cc_a, YEAR).reserve_carry_in_cents == 1000


def test_carry_in_override_can_be_reset_to_the_previous_year(
    planning: PlanningService, world: World
) -> None:
    _save(planning, world, year=YEAR - 1, base=60000)
    _save(planning, world, base=10000, carry_in=1000)

    planning.save_plan(
        world.cc_a,
        YEAR,
        base_budget_cents=10000,
        reserve_carry_in_cents=1000,
        months=[],
        actor_id=world.actor,
        carry_in_automatic=True,
    )

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.reserve_carry_in_cents == 60000 and not view.reserve_carry_in_manual
    _save(planning, world, year=YEAR - 1, base=70000)
    assert planning.get_plan_view(world.cc_a, YEAR).reserve_carry_in_cents == 70000


def test_overridden_carry_in_is_fixed_after_january_is_closed(
    planning: PlanningService, database: Database, world: World
) -> None:
    from meine_kasse.infrastructure.database.models import PeriodClosureModel

    _save(planning, world, year=YEAR - 1, base=60000)
    _save(planning, world, base=10000, carry_in=1000)
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

    view = planning.get_plan_view(world.cc_a, YEAR)
    assert not view.reserve_carry_in_editable and view.reserve_carry_in_cents == 1000
    with pytest.raises(PeriodError, match="vortrag"):
        _save(planning, world, base=10000, carry_in=2000)
    with pytest.raises(PeriodError, match="vortrag"):
        planning.save_plan(
            world.cc_a,
            YEAR,
            base_budget_cents=10000,
            months=[],
            actor_id=world.actor,
            carry_in_automatic=True,
        )


def test_carry_in_cannot_change_after_january_is_closed(
    planning: PlanningService, database: Database, world: World
) -> None:
    from meine_kasse.infrastructure.database.models import PeriodClosureModel

    _save(planning, world, carry_in=1000)
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

    with pytest.raises(PeriodError, match="vortrag"):
        _save(planning, world, carry_in=2000)
    assert not planning.get_plan_view(world.cc_a, YEAR).reserve_carry_in_editable


def test_unused_reserve_is_carried_into_the_next_year_and_follows_later_bookings(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world, year=YEAR - 1, base=120000)
    _save(planning, world, base=120000)
    assert planning.get_plan_view(world.cc_a, YEAR).reserve_carry_in_cents == 120000

    _spend(bookings, world, origin=date(2025, 3, 5), cents=50000, booked=date(2026, 4, 1))

    previous = planning.get_plan_view(world.cc_a, YEAR - 1)
    current = planning.get_plan_view(world.cc_a, YEAR)
    assert previous.reserve_carry_out_cents == 120000 - 30000  # März: 3 x 100,00 € verfügbar
    assert current.reserve_carry_in_cents == previous.reserve_carry_out_cents
    assert current.reserve_carry_out_cents == current.reserve_carry_in_cents + 120000


# Entlastung durch Ist


def test_actual_spending_releases_the_reserve_of_its_plan_month(
    planning: PlanningService, bookings: BookingService, database: Database, world: World
) -> None:
    _save(planning, world)

    _spend(bookings, world, origin=date(2026, 3, 5), cents=25000)

    assert _release(planning, world) == {3: 25000}
    view = planning.get_plan_view(world.cc_a, YEAR)
    assert view.months[2].reserve_balance_cents == 30000 - 25000
    assert view.months[3].reserve_balance_cents == 40000 - 25000
    assert view.reserve_carry_out_cents == 120000 - 25000


def test_release_is_limited_to_the_available_reserve(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world)

    _spend(bookings, world, origin=date(2026, 1, 5), cents=25000)

    assert _release(planning, world) == {1: 10000}
    assert planning.get_plan_view(world.cc_a, YEAR).months[0].reserve_balance_cents == 0


def test_later_bookings_see_the_release_of_earlier_months(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world)
    _spend(bookings, world, origin=date(2026, 1, 5), cents=10000)

    _spend(bookings, world, origin=date(2026, 2, 5), cents=15000)

    assert _release(planning, world) == {1: 10000, 2: 10000}


def test_changing_and_deleting_a_booking_recalculates_the_release(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world)
    first = _spend(bookings, world, origin=date(2026, 2, 5), cents=15000)
    _spend(bookings, world, origin=date(2026, 3, 5), cents=10000)
    assert _release(planning, world) == {2: 15000, 3: 10000}

    current = bookings.get_booking(first)
    bookings.update(
        first,
        booking_type=current.booking_type,
        entry_side=current.entry_side,
        amount_cents=15000,
        booking_date=current.booking_date,
        origin_date=date(2026, 6, 5),
        leading=Stelle(ObjectKind.COST_CENTER, world.cc_a),
        second=Stelle(ObjectKind.ACCOUNT, world.giro),
        actor_id=world.actor,
    )
    assert _release(planning, world) == {3: 10000, 6: 15000}

    bookings.delete(first, actor_id=world.actor)
    assert _release(planning, world) == {3: 10000}


def test_a_refund_gives_back_at_most_the_earlier_release(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world)
    _spend(bookings, world, origin=date(2026, 2, 5), cents=15000)

    _spend(bookings, world, origin=date(2026, 3, 5), cents=40000, side=Side.CREDIT)

    assert _release(planning, world) == {2: 15000, 3: -15000}
    assert planning.get_plan_view(world.cc_a, YEAR).reserve_carry_out_cents == 120000


def test_reversal_restores_the_reserve(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world)
    booking_id = _spend(bookings, world, origin=date(2026, 3, 5), cents=25000)

    bookings.reverse(booking_id, booking_date=date(2026, 5, 12), actor_id=world.actor)

    assert _release(planning, world) == {}
    assert planning.get_plan_view(world.cc_a, YEAR).reserve_carry_out_cents == 120000


def test_cost_centers_without_plan_have_no_reserve(
    bookings: BookingService, database: Database, world: World
) -> None:
    _spend(bookings, world, origin=date(2026, 3, 5), cents=25000, cost_center=world.cc_free)

    assert _stored_actuals(database) == {}


def test_release_is_not_changed_by_the_order_of_bookings(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world)
    for month, cents in ((4, 20000), (2, 15000), (3, 5000)):
        _spend(bookings, world, origin=date(2026, month, 5), cents=cents)
    expected = _release(planning, world)

    bookings.rebuild_projections()

    assert _release(planning, world) == expected == {2: 15000, 3: 5000, 4: 20000}


# Hinweise und Anzeige beim Buchen


def test_notice_when_the_reserve_does_not_cover_the_payment(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world)

    _spend(bookings, world, origin=date(2026, 1, 5), cents=25000)

    notice = bookings.reserve_notice(world.cc_a, date(2026, 1, 5))
    assert notice is not None
    assert "01/2026" in notice and "150,00 €" in notice and "dennoch ausgeführt" in notice


def test_no_notice_when_the_reserve_covers_the_payment_or_none_exists(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _spend(bookings, world, origin=date(2026, 1, 5), cents=25000)
    assert bookings.reserve_notice(world.cc_a, date(2026, 1, 5)) is None

    _save(planning, world)
    _spend(bookings, world, origin=date(2026, 6, 5), cents=10000)
    assert bookings.reserve_notice(world.cc_a, date(2026, 6, 5)) is None


def test_no_notice_when_every_month_is_planned_directly(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world, plans=[MonthPlanInput(month, 10000) for month in range(1, 13)])

    _spend(bookings, world, origin=date(2026, 1, 5), cents=25000)

    assert bookings.reserve_notice(world.cc_a, date(2026, 1, 5)) is None


def test_cost_center_info_shows_the_reserve_balance_up_to_the_plan_month(
    planning: PlanningService, bookings: BookingService, world: World
) -> None:
    _save(planning, world, carry_in=5000)
    _spend(bookings, world, origin=date(2026, 2, 5), cents=7000)

    info = bookings.cost_center_info(world.cc_a, date(2026, 3, 1))

    assert info.reserve_cents == 5000 + 3 * 10000 - 7000


# Neuaufbau, Start und Abschluss


def test_refresh_repairs_stale_projections_and_audits_only_when_something_changed(
    planning: PlanningService, bookings: BookingService, database: Database, world: World
) -> None:
    _save(planning, world)
    _spend(bookings, world, origin=date(2026, 3, 5), cents=25000)
    with database.session_factory() as session:
        for row in session.scalars(select(MonthlyActualModel)):
            row.reserve_actual_cents = 1
        for plan in session.scalars(select(CostCenterPlanModel)):
            plan.reserve_carry_out_cents = 7
        session.commit()

    planning.refresh_reserves()

    assert _release(planning, world) == {3: 25000}
    assert planning.get_plan_view(world.cc_a, YEAR).reserve_carry_out_cents == 95000
    names = _audit_names(database)
    assert names.count("RESERVES_REFRESHED") == 1
    planning.refresh_reserves()
    assert _audit_names(database).count("RESERVES_REFRESHED") == 1


def _audit_names(database: Database) -> list[str]:
    with database.session_factory() as session:
        return [row.name for row in session.scalars(select(AuditLogModel))]


def test_inconsistent_reserve_blocks_month_closing_until_rebuilt(
    planning: PlanningService,
    bookings: BookingService,
    closing: ClosingService,
    booking_control: BookingControlService,
    database: Database,
    world: World,
) -> None:
    booking_control.update(planning_enabled=False, current_year=YEAR, current_month=5)
    _save(planning, world)
    _spend(bookings, world, origin=date(2026, 5, 5), cents=25000)
    with database.session_factory() as session:
        actual = session.scalars(select(MonthlyActualModel)).one()
        actual.reserve_actual_cents = 1
        session.commit()

    with pytest.raises(ValidationError, match="Rückstellung") as error:
        closing.close_month(actor_id=world.actor)
    assert "100 Lebensmittel" in str(error.value)

    bookings.rebuild_projections(actor_id=world.actor)
    closing.close_month(actor_id=world.actor)


def test_preview_does_not_write_anything(
    planning: PlanningService, database: Database, world: World
) -> None:
    preview = planning.preview_reserve(
        world.cc_a,
        YEAR,
        base_budget_cents=120000,
        carry_in_cents=0,
        months=[MonthPlanInput(3, 60000), MonthPlanInput(9, 60000)],
    )

    assert [preview.reserve_plan[m] for m in (1, 2, 3)] == [10000] * 3
    assert preview.carry_out_cents == 30000 and len(preview.notices) == 1
    with database.session_factory() as session:
        assert session.scalars(select(CostCenterPlanModel)).first() is None
        assert session.scalars(select(MonthlyPlanModel)).first() is None


def test_migration_marks_existing_reserves_as_manual(database: Database, world: World) -> None:
    from meine_kasse.infrastructure.database.migrate import downgrade_database, upgrade_database

    with database.session_factory() as session:
        plan = CostCenterPlanModel(cost_center_id=world.cc_a, year=YEAR, base_budget_cents=1000)
        session.add(plan)
        session.flush()
        session.add(MonthlyPlanModel(cost_center_plan_id=plan.id, month=1, reserve_plan_cents=500))
        session.add(MonthlyPlanModel(cost_center_plan_id=plan.id, month=2, plan_cents=100))
        session.commit()
    downgrade_database(database.engine, "0005")
    upgrade_database(database.engine, "0006")
    upgrade_database(database.engine)

    with database.session_factory() as session:
        rows = {
            row.month: row.reserve_is_manual for row in session.scalars(select(MonthlyPlanModel))
        }
    assert rows == {1: True, 2: False}
