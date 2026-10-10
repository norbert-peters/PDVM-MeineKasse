from collections.abc import Callable
from datetime import date

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from meine_kasse.domain.entities import CostCenter, User
from meine_kasse.domain.enums import CostCenterKind
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.infrastructure.database.base import Base
from meine_kasse.infrastructure.database.models import (
    BookingControlModel,
    BookingLegModel,
    BookingModel,
    CostCenterModel,
    UserModel,
)
from meine_kasse.infrastructure.database.session import Database


def _user(name: str = "anna") -> User:
    return User(
        id=new_id(),
        name=name,
        last_name="Muster",
        first_name="Anna",
        address="",
        password_hash="hash",
        initial_password_hash=None,
        must_change_password=False,
        password_changed_at=None,
    )


def _cost_center(number: str = "100") -> CostCenter:
    return CostCenter(
        id=new_id(),
        name="Lebensmittel",
        number=number,
        valid_from=date(2026, 1, 1),
        kind=CostCenterKind.STANDARD,
        notes="",
    )


def test_foreign_keys_are_enabled(database: Database) -> None:
    with database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_migration_matches_models(database: Database) -> None:
    with database.engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_all_tables_have_guid_primary_key_and_name(database: Database) -> None:
    inspector = inspect(database.engine)
    for table in Base.metadata.tables:
        columns = {column["name"] for column in inspector.get_columns(table)}
        assert {"id", "name", "created_at", "updated_at"} <= columns, table


def test_uncommitted_work_is_rolled_back(uow_factory: Callable[[], UnitOfWork]) -> None:
    with uow_factory() as uow:
        uow.users.add(_user())
    with uow_factory() as uow:
        assert uow.users.count() == 0


def test_committed_work_is_persisted(uow_factory: Callable[[], UnitOfWork]) -> None:
    with uow_factory() as uow:
        uow.users.add(_user())
        uow.commit()
    with uow_factory() as uow:
        assert uow.users.count() == 1


def test_user_name_lookup_ignores_case(uow_factory: Callable[[], UnitOfWork]) -> None:
    with uow_factory() as uow:
        uow.users.add(_user("Anna"))
        uow.commit()
        found = uow.users.get_by_name("  aNNa ")
    assert found is not None
    assert found.name == "Anna"


def test_user_repr_hides_hashes() -> None:
    assert "hash" not in repr(_user())


def test_cost_center_number_is_unique(uow_factory: Callable[[], UnitOfWork]) -> None:
    with uow_factory() as uow:
        uow.cost_centers.add(_cost_center("100"))
        uow.commit()
    with uow_factory() as uow, pytest.raises(IntegrityError):
        uow.cost_centers.add(_cost_center("100"))


def _insert_booking(database: Database, amount_cents: int) -> str:
    with database.session_factory() as session:
        user = _user()
        cost_center = _cost_center()
        session.add_all(
            [
                _user_model(user),
                CostCenterModel(
                    id=cost_center.id,
                    name=cost_center.name,
                    number=cost_center.number,
                    valid_from=cost_center.valid_from,
                ),
            ]
        )
        session.flush()
        booking = BookingModel(
            origin_date=date(2026, 5, 1),
            booking_date=date(2026, 5, 1),
            booking_type="COST_CENTER_TO_ACCOUNT",
            entry_side="DEBIT",
            amount_cents=amount_cents,
            fiscal_year=2026,
            fiscal_month=5,
            created_by_user_id=user.id,
        )
        session.add(booking)
        session.commit()
        return booking.id


def _user_model(user: User) -> UserModel:
    return UserModel(id=user.id, name=user.name, password_hash=user.password_hash)


@pytest.mark.parametrize("amount", [-5000, 5000])
def test_signed_amounts_are_stored(database: Database, amount: int) -> None:
    booking_id = _insert_booking(database, amount)
    with database.session_factory() as session:
        assert session.get(BookingModel, booking_id).amount_cents == amount  # type: ignore[union-attr]


def test_zero_amount_is_rejected_by_database(database: Database) -> None:
    with pytest.raises(IntegrityError):
        _insert_booking(database, 0)


def test_leg_needs_exactly_one_stelle(database: Database) -> None:
    booking_id = _insert_booking(database, 100)
    with database.session_factory() as session:
        session.add(BookingLegModel(booking_id=booking_id, position=1, side="DEBIT"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_only_one_active_booking_control(database: Database) -> None:
    with database.session_factory() as session:
        session.add(BookingControlModel(current_year=2026, current_month=5))
        session.commit()
        session.add(BookingControlModel(current_year=2026, current_month=6))
        with pytest.raises(IntegrityError):
            session.commit()
