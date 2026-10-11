import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from meine_kasse.logging_setup import (
    LOG_FILE_NAME,
    LOGGER_NAME,
    configure_logging,
    install_excepthook,
    user_message,
)


@pytest.fixture(autouse=True)
def clean_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    yield
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def flush() -> None:
    for handler in logging.getLogger(LOGGER_NAME).handlers:
        handler.flush()


def test_configure_logging_creates_the_log_file(tmp_path: Path) -> None:
    path = configure_logging(tmp_path / "logs")

    logging.getLogger(LOGGER_NAME).info("Hallo Protokoll")
    flush()

    assert path == tmp_path / "logs" / LOG_FILE_NAME
    assert "Hallo Protokoll" in path.read_text(encoding="utf-8")


def test_configuring_twice_does_not_duplicate_lines(tmp_path: Path) -> None:
    configure_logging(tmp_path)
    path = configure_logging(tmp_path)

    logging.getLogger(LOGGER_NAME).info("nur einmal")
    flush()

    assert path.read_text(encoding="utf-8").count("nur einmal") == 1


def raise_and_capture() -> tuple[type[BaseException], BaseException, object]:
    try:
        raise RuntimeError("kaputt")
    except RuntimeError:
        exc_info = sys.exc_info()
        assert exc_info[0] is not None and exc_info[1] is not None
        return exc_info[0], exc_info[1], exc_info[2]


def test_unhandled_exception_is_logged_with_stacktrace_and_reported_without_it(
    tmp_path: Path,
) -> None:
    path = configure_logging(tmp_path)
    reported: list[str] = []
    install_excepthook(path, report=reported.append)

    exc_type, exc, tb = raise_and_capture()
    sys.excepthook(exc_type, exc, tb)  # type: ignore[arg-type]
    flush()

    content = path.read_text(encoding="utf-8")
    assert "Unerwarteter Fehler" in content and "Traceback" in content and "kaputt" in content
    (message,) = reported
    assert str(path) in message
    assert "Traceback" not in message and "kaputt" not in message


def test_keyboard_interrupt_is_not_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = configure_logging(tmp_path)
    reported: list[str] = []
    install_excepthook(path, report=reported.append)

    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)

    assert reported == []


def test_a_failing_reporter_never_raises(tmp_path: Path) -> None:
    path = configure_logging(tmp_path)

    def broken(_text: str) -> None:
        raise OSError("keine Oberfläche")

    install_excepthook(path, report=broken)
    exc_type, exc, tb = raise_and_capture()
    sys.excepthook(exc_type, exc, tb)  # type: ignore[arg-type]
    flush()

    assert "Die Fehlermeldung konnte nicht angezeigt werden" in path.read_text(encoding="utf-8")


def test_user_message_names_the_log_file() -> None:
    assert "C:\\x\\meine_kasse.log" in user_message(Path("C:\\x\\meine_kasse.log"))
