import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from meine_kasse import main as main_module
from meine_kasse.config import DATABASE_ENV_VARIABLE
from meine_kasse.logging_setup import LOGGER_NAME
from meine_kasse.selftest import SELFTEST_FLAG, run_selftest


@pytest.fixture(autouse=True)
def clean_logger() -> Iterator[None]:
    yield
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_selftest_passes_in_a_temporary_database(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="meine_kasse.selftest"):
        assert run_selftest() == 0

    messages = caplog.text
    for step in (
        "Anwender anlegen und anmelden (Argon2)",
        "Stammdaten anlegen",
        "Buchen",
        "Monatsabschluss mit Signatur",
        "Datensicherung",
    ):
        assert f"Selbsttest OK: {step}" in messages
    assert "Selbsttest bestanden" in messages


def test_selftest_never_touches_the_configured_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "echt.sqlite"
    monkeypatch.setenv(DATABASE_ENV_VARIABLE, str(configured))

    assert run_selftest() == 0
    assert not configured.exists()


def test_main_runs_the_selftest_without_a_gui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DATABASE_ENV_VARIABLE, str(tmp_path / "x.sqlite"))
    monkeypatch.setattr(sys, "argv", ["MeineKasse.exe", SELFTEST_FLAG])

    assert main_module.main() == 0
    assert (tmp_path / "logs" / "meine_kasse.log").exists()
