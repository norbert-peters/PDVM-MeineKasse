from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import inspect

from meine_kasse.application.services.auth_service import AuthService
from meine_kasse.application.services.user_settings_service import TableSort, UserSettingsService
from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.infrastructure.database.migrate import upgrade_database
from meine_kasse.infrastructure.database.session import Database


@pytest.fixture
def settings(uow_factory: Callable[[], UnitOfWork]) -> UserSettingsService:
    return UserSettingsService(uow_factory)


@pytest.fixture
def two_users(auth: AuthService) -> tuple[str, str]:
    first = auth.create_user(
        name="eins", last_name="A", first_name="A", initial_password="Erst-1234"
    )
    second = auth.create_user(
        name="zwei", last_name="B", first_name="B", initial_password="Erst-1234"
    )
    return first, second


def test_missing_setting_returns_none(
    settings: UserSettingsService, two_users: tuple[str, str]
) -> None:
    assert settings.get(two_users[0], "table.bookings") is None
    assert settings.get_table_sort(two_users[0], "bookings") is None


def test_setting_round_trips_and_overwrites(
    settings: UserSettingsService, two_users: tuple[str, str]
) -> None:
    first, _second = two_users

    settings.set(first, "demo", {"a": 1, "text": "Größe"})
    settings.set(first, "demo", {"a": 2})

    assert settings.get(first, "demo") == {"a": 2}


def test_settings_are_separate_per_user(
    settings: UserSettingsService, two_users: tuple[str, str]
) -> None:
    first, second = two_users

    settings.save_table_sort(first, "bookings", TableSort("Datum", ascending=False))
    settings.save_table_sort(second, "bookings", TableSort("Soll", ascending=True))

    assert settings.get_table_sort(first, "bookings") == TableSort("Datum", False)
    assert settings.get_table_sort(second, "bookings") == TableSort("Soll", True)


def test_removing_the_sort_clears_it(
    settings: UserSettingsService, two_users: tuple[str, str]
) -> None:
    first, _second = two_users
    settings.save_table_sort(first, "bookings", TableSort("Datum"))

    settings.save_table_sort(first, "bookings", None)

    assert settings.get_table_sort(first, "bookings") is None


def test_unreadable_values_are_ignored(
    settings: UserSettingsService,
    two_users: tuple[str, str],
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    first, _second = two_users
    with uow_factory() as uow:
        uow.user_settings.save(first, "table.kaputt", "{nicht json")
        uow.user_settings.save(first, "table.liste", "[1, 2]")
        uow.user_settings.save(first, "table.ohnespalte", '{"order": "asc"}')
        uow.commit()

    assert settings.get(first, "table.kaputt") is None
    assert settings.get(first, "table.liste") is None
    assert settings.get_table_sort(first, "ohnespalte") is None


@pytest.mark.parametrize("key", ["", "   ", "x" * 201])
def test_invalid_keys_are_rejected(
    settings: UserSettingsService, two_users: tuple[str, str], key: str
) -> None:
    with pytest.raises(ValidationError):
        settings.set(two_users[0], key, {})


def test_migration_creates_the_table(tmp_path: Path) -> None:
    fresh = Database.from_file(tmp_path / "migration.sqlite")
    try:
        upgrade_database(fresh.engine, "0003")
        assert "user_settings" not in _tables(fresh)

        upgrade_database(fresh.engine, "head")

        assert "user_settings" in _tables(fresh)
    finally:
        fresh.dispose()


def _tables(database: Database) -> set[str]:
    return set(inspect(database.engine).get_table_names())
