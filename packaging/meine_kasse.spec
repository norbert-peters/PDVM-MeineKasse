# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spezifikation für Meine Kasse (Windows, Ordner-Variante).

Aufruf über `packaging\\build.ps1`. Die Datenbank-Migrationen werden als Dateien mitgeliefert,
weil Alembic sie zur Laufzeit aus dem Dateisystem lädt.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
source = root / "src"
migrations = source / "meine_kasse" / "infrastructure" / "database" / "migrations"

datas = [(str(migrations), "meine_kasse/infrastructure/database/migrations")]
binaries = []
hiddenimports = collect_submodules("alembic") + collect_submodules("sqlalchemy.dialects.sqlite")
# env.py der Migrationen wird zur Laufzeit als Datei geladen; PyInstaller sieht dessen Importe nicht
hiddenimports += ["logging.config"]

for package in ("argon2", "_argon2_cffi_bindings"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

analysis = Analysis(
    [str(root / "packaging" / "start_meine_kasse.py")],
    pathex=[str(source)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "mypy", "ruff", "PySide6.QtWebEngineCore", "PySide6.QtQml"],
    noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="MeineKasse",
    console=False,
    disable_windowed_traceback=False,
)
COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="MeineKasse",
)
