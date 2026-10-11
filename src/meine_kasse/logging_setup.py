"""Protokollierung in eine lokale Datei und Behandlung unerwarteter Fehler.

Die Anwendung läuft ohne Konsole. Unerwartete Fehler werden deshalb mit Stacktrace in die
Protokolldatei geschrieben, der Anwender sieht nur eine allgemeine Meldung mit dem Dateipfad.
Es werden nie Passwörter oder Eingaben protokolliert.
"""

import logging
import sys
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

LOGGER_NAME = "meine_kasse"
LOG_FILE_NAME = "meine_kasse.log"
_MAX_BYTES = 1_000_000
_BACKUPS = 3
_HANDLER_MARK = "_meine_kasse_handler"

ErrorReporter = Callable[[str], None]


def configure_logging(directory: Path) -> Path:
    """Richtet die Protokolldatei (mit Rotation) ein und gibt ihren Pfad zurück."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_FILE_NAME
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    for existing in list(logger.handlers):
        if getattr(existing, _HANDLER_MARK, False):
            logger.removeHandler(existing)
            existing.close()
    handler = RotatingFileHandler(path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    setattr(handler, _HANDLER_MARK, True)
    logger.addHandler(handler)
    return path


def user_message(log_path: Path) -> str:
    return (
        "Es ist ein unerwarteter Fehler aufgetreten. Ihre Daten wurden nicht verändert, "
        "soweit der Vorgang nicht abgeschlossen war.\n\n"
        f"Details stehen in der Protokolldatei:\n{log_path}"
    )


def install_excepthook(log_path: Path, report: ErrorReporter | None = None) -> None:
    """Protokolliert unbehandelte Ausnahmen und meldet sie dem Anwender ohne Stacktrace."""
    logger = logging.getLogger(LOGGER_NAME)

    def hook(
        exc_type: type[BaseException], exc: BaseException, traceback: TracebackType | None
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, traceback)
            return
        logger.critical("Unerwarteter Fehler", exc_info=(exc_type, exc, traceback))
        if report is not None:
            try:
                report(user_message(log_path))
            except Exception:  # noqa: BLE001 - die Fehlermeldung darf nie selbst abstürzen
                logger.exception("Die Fehlermeldung konnte nicht angezeigt werden")

    sys.excepthook = hook
