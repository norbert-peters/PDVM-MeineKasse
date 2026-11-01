from pathlib import Path

import pytest

from meine_kasse.config import DATABASE_ENV_VARIABLE, data_dir, database_path, log_dir


@pytest.fixture
def local_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv(DATABASE_ENV_VARIABLE, raising=False)
    return tmp_path


def test_default_locations_are_outside_the_program_directory(local_app_data: Path) -> None:
    assert data_dir() == local_app_data / "MeineKasse"
    assert database_path() == local_app_data / "MeineKasse" / "meine_kasse.sqlite"
    assert log_dir() == local_app_data / "MeineKasse" / "logs"


def test_database_can_be_overridden_and_logs_follow(
    local_app_data: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "test" / "kasse.sqlite"
    monkeypatch.setenv(DATABASE_ENV_VARIABLE, str(custom))

    assert database_path() == custom
    assert log_dir() == custom.parent / "logs"


def test_packaged_data_lives_next_to_the_executable(
    local_app_data: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exe = tmp_path / "PDVM_MeineKasse" / "MeineKasse.exe"
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(exe))

    assert data_dir() == exe.parent.resolve() / "Daten"
    assert database_path() == exe.parent.resolve() / "Daten" / "meine_kasse.sqlite"
    assert log_dir() == exe.parent.resolve() / "Daten" / "logs"


def test_fallback_without_local_app_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv(DATABASE_ENV_VARIABLE, raising=False)
    assert data_dir().name == "MeineKasse"
    assert Path.home() in data_dir().parents
