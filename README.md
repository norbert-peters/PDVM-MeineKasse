# Meine Kasse

Deutschsprachige Desktop-Anwendung für eine einfache Haushaltsbuchhaltung auf Kostenstellen und Konten (Python, PySide6, SQLite).

Verbindliche Vorgaben:

- [Architekturvorgabe](./ARCHITEKTURVORGABE.md)
- [Entwicklungsregeln](./ENTWICKLUNGSREGELN.md)
- Ausgangsdokument: `PDVM Meine Kasse.docx`

## Stand

Umgesetzt (erste Schritte):

- Schichtenstruktur `domain` / `application` / `infrastructure` / `presentation`
- SQLite mit Alembic-Migration für alle Tabellen der Architekturvorgabe (Fremdschlüssel aktiv, GUID-Primärschlüssel)
- Anmeldung mit Argon2id, Pflicht-Passwortwechsel beim erstmaligen Passwort, Passwort-Reset auf das erstmalige Passwort
- Anlage von Kostenstellen und Konten (eindeutige Nummern, IBAN-Prüfung)
- Fachregeln als reine Funktionen: Buchungsstellen und Wirkung, Ansatzsperre, Buchungszeitraum, Geld-/Prozentwerte
- Oberfläche: Erstanwender, Login, Passwortwechsel, Hauptmenü (Fachdialoge folgen)

Noch nicht umgesetzt: Buchung erfassen, Ansatzumbuchung, Planung, Monats-/Jahresabschluss, Auswertungen.

## Einrichten und Starten

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m meine_kasse.main
```

Die Datenbank liegt standardmäßig unter `%LOCALAPPDATA%\MeineKasse\meine_kasse.sqlite`. Mit der Umgebungsvariable `MEINE_KASSE_DB` kann ein anderer Pfad gesetzt werden. Beim Start wird das Schema automatisch migriert.

## Qualitätssicherung

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\mypy.exe
```

## Schemaänderungen

Schemaänderungen erfolgen ausschließlich über Alembic-Migrationen:

```powershell
.\.venv\Scripts\alembic.exe revision --autogenerate -m "Beschreibung"
```

Die erzeugte Migration ist zu prüfen. Der Test `test_migration_matches_models` stellt sicher, dass Migrationen und Modelle übereinstimmen.
