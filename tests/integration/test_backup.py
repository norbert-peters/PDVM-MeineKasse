import sqlite3
from datetime import date
from pathlib import Path

import pytest

from conftest import World
from meine_kasse.application.services.backup_service import BackupService
from meine_kasse.domain.errors import ValidationError
from meine_kasse.infrastructure.database.session import Database


def count_rows(path: Path, table: str) -> int:
    connection = sqlite3.connect(path)
    try:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        connection.close()


def test_backup_is_a_complete_and_consistent_copy(
    database: Database, tmp_path: Path, world: World
) -> None:
    target = tmp_path / "sicherung" / "kopie.sqlite"

    database.backup_to(target)

    assert count_rows(target, "users") == 1
    assert count_rows(target, "cost_centers") == 3
    assert count_rows(target, "accounts") == 2
    connection = sqlite3.connect(target)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        connection.close()


def test_backup_replaces_an_existing_file(database: Database, tmp_path: Path, world: World) -> None:
    target = tmp_path / "kopie.sqlite"
    target.write_text("altes Zeug")

    database.backup_to(target)

    assert count_rows(target, "users") == 1


def test_backup_service_adds_the_suffix(database: Database, tmp_path: Path, world: World) -> None:
    service = BackupService(database, tmp_path / "test.sqlite", today=lambda: date(2026, 5, 15))

    assert service.suggested_file_name() == "meine_kasse_2026-05-15.sqlite"
    created = service.create_backup(tmp_path / "meine_sicherung")

    assert created == tmp_path / "meine_sicherung.sqlite"
    assert count_rows(created, "users") == 1


def test_backup_must_not_overwrite_the_running_database(database: Database, tmp_path: Path) -> None:
    live = tmp_path / "test.sqlite"
    service = BackupService(database, live)

    with pytest.raises(ValidationError, match="laufende Datenbank"):
        service.create_backup(live)
    assert count_rows(live, "users") == 0
