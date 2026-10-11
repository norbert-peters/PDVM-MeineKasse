"""Selbsttest für das Installationspaket: `MeineKasse.exe --selbsttest`.

Er läuft ohne Oberfläche in einer **temporären** Datenbank und berührt nie die echten Daten.
Geprüft werden die Schichten, die im gepackten Programm am ehesten fehlen: Migrationen,
Passwort-Hash (Argon2), Buchen, Abschluss mit Signatur und Datensicherung.
"""

import logging
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

from meine_kasse.bootstrap import Container, build_container
from meine_kasse.domain.enums import AccountType, BookingType, ObjectKind, Side
from meine_kasse.domain.services.booking_rules import Stelle

logger = logging.getLogger("meine_kasse.selftest")
SELFTEST_FLAG = "--selbsttest"
_PASSWORD = "Selbsttest-123"


def _user_and_login(container: Container, state: dict[str, str]) -> None:
    user_id = container.auth.create_user(
        name="selbsttest", last_name="Test", first_name="Selbst", initial_password=_PASSWORD
    )
    login = container.auth.login("selbsttest", _PASSWORD)
    if login.user_id != user_id or not login.must_change_password:
        raise AssertionError("Die Anmeldung mit dem erstmaligen Passwort ist fehlgeschlagen.")
    state["user"] = user_id


def _master_data(container: Container, state: dict[str, str]) -> None:
    state["cost_center"] = container.master_data.create_cost_center(
        number="100", name="Selbsttest", valid_from=date(2026, 1, 1)
    )
    state["account"] = container.master_data.create_account(
        number="1000", name="Selbsttestkonto", account_type=AccountType.CHECKING
    )


def _booking(container: Container, state: dict[str, str]) -> None:
    day = container.bookings.default_booking_date()
    container.bookings.post(
        booking_type=BookingType.COST_CENTER_TO_ACCOUNT,
        entry_side=Side.DEBIT,
        amount_cents=1234,
        booking_date=day,
        origin_date=day,
        leading=Stelle(ObjectKind.COST_CENTER, state["cost_center"]),
        second=Stelle(ObjectKind.ACCOUNT, state["account"]),
        actor_id=state["user"],
    )
    if container.bookings.account_balance(state["account"]) != -1234:
        raise AssertionError("Der Kontostand stimmt nach der Buchung nicht.")


def _closing(container: Container, state: dict[str, str]) -> None:
    container.closing.close_month(actor_id=state["user"])
    checks = container.closing.verify_closures()
    if not checks or not all(check.ok for check in checks):
        raise AssertionError("Die Signatur des Abschlusses ist ungültig.")


def _backup(container: Container, state: dict[str, str], directory: Path) -> None:
    created = container.backup.create_backup(directory / "sicherung.sqlite")
    if not created.exists() or created.stat().st_size == 0:
        raise AssertionError("Die Datensicherung wurde nicht erstellt.")


def run_selftest() -> int:
    """Gibt 0 zurück, wenn alle Prüfungen bestanden wurden, sonst 1."""
    failures = 0
    with tempfile.TemporaryDirectory(prefix="meine_kasse_selbsttest_") as directory:
        container = build_container(Path(directory) / "selbsttest.sqlite")
        state: dict[str, str] = {}
        steps: list[tuple[str, Callable[[], None]]] = [
            ("Anwender anlegen und anmelden (Argon2)", lambda: _user_and_login(container, state)),
            ("Stammdaten anlegen", lambda: _master_data(container, state)),
            ("Buchen", lambda: _booking(container, state)),
            ("Monatsabschluss mit Signatur", lambda: _closing(container, state)),
            ("Datensicherung", lambda: _backup(container, state, Path(directory))),
        ]
        try:
            for name, step in steps:
                try:
                    step()
                except Exception:  # noqa: BLE001 - jeder Fehler ist ein Fehlschlag des Tests
                    failures += 1
                    logger.exception("Selbsttest FEHLER: %s", name)
                else:
                    logger.info("Selbsttest OK: %s", name)
        finally:
            container.database.dispose()
    logger.info("Selbsttest %s", "bestanden" if failures == 0 else f"fehlgeschlagen ({failures})")
    return 0 if failures == 0 else 1
