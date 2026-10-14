"""Zeitpunkt des Builds, damit der Stand eines Pakets eindeutig erkennbar ist.

`packaging\\build.ps1` erzeugt beim Start des Builds die Datei `_build_info.py` (nicht in der
Versionsverwaltung). Im Entwicklungsstand fehlt sie, dann gibt es keinen Build-Zeitpunkt.
"""

from datetime import datetime

try:
    from meine_kasse import _build_info  # type: ignore[attr-defined,unused-ignore]
except ImportError:
    _build_info = None


def build_time() -> datetime | None:
    """Beginn des Builds (lokale Zeit) oder `None` im Entwicklungsstand."""
    raw = getattr(_build_info, "BUILD_TIMESTAMP", None)
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def build_label() -> str:
    """Anzeigetext, z. B. `Build vom 14.10.2026 13:20:05`."""
    built = build_time()
    if built is None:
        return "Entwicklungsstand (kein Paket-Build)"
    return f"Build vom {built.strftime('%d.%m.%Y %H:%M:%S')}"
