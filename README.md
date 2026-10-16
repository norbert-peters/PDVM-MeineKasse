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
- Anlage, Änderung und (De-)Aktivierung von Kostenstellen, Konten und Anwendern mit Dialogen im Menü „Stammdaten“
- Pflege der Passwörter durch den Anwender (erstmaliges Passwort festlegen, auf erstmaliges Passwort zurücksetzen)
- Fachregeln als reine Funktionen: Buchungsstellen und Wirkung, Ansatzsperre, Buchungszeitraum, Geld-/Prozentwerte
- Buchungen: Erfassen, Ändern und Löschen in offenen Monaten, Storno per Minusbuchung, alle drei Buchungsarten (Kostenstelle → Konto, Umbuchung zwischen Konten mit je einer Kostenstelle als zwei Buchungssätze, Ansatzumbuchung)
- Plan-Ist-Fortschreibung und Ansatzsperre in einer Transaktion mit der Buchung, Neuaufbau der Projektionen aus den Buchungen
- Buchungssteuerung (aktueller Buchungsmonat, Planung ein/aus) und Buchungsliste mit sichtbarem Monatsstatus (frei/fix)
- Planung je Kostenstelle: Haushaltsansatz, Monatswerte (Plan-Ansatz, Art, Rückstellung Plan), Rückstellungsüberträge, Soll-/Ist-Vergleich je Monat; Eingabehilfen „gleichmäßig verteilen“ und „Quartalsbeträge“
- Einnahmenplanung: Kostenstellen der Art „Einnahme“ (z. B. Rente, PV-Entgelt, Orgelspiel, Zinsen) mit erwarteter Einnahme je Monat, Vergleich mit der gebuchten Einnahme und Weitergabe per Ansatzumbuchung an Kostenstellen mit Plan; Modus „nach Plan verfügbar“ oder „nur nach Ist verfügbar“
- Monats- und Jahresabschluss mit SHA-256-Signatur, lückenloser Reihenfolge, Konsistenzprüfung vor dem Abschluss und Integritätsprüfung aller Abschlüsse
- Oberfläche: Erstanwender, Login, Passwortwechsel, Hauptmenü, Stammdaten-, Buchungs-, Planungs- und Abschlussdialoge

- Wiedereröffnen von Abschlüssen nur in umgekehrter Reihenfolge, mit Pflichtbegründung und dauerhafter Dokumentation (Historie im Abschlussdialog)
- Anfangssalden (Jahresvortrag) der Konten: editierbar ohne Vorjahr bis zum Abschluss des Januars, sonst aus dem Vorjahr abgeleitet

Noch nicht umgesetzt: Auswertungen.

Ablauf eines Monats: Buchungen erfassen, Plan-Ist in der Planung ansehen, dann im Menü „Abschluss“ den aktuellen Buchungsmonat abschließen. Der Buchungsmonat rückt automatisch auf den Folgemonat. Sind alle zwölf Monate abgeschlossen, kann das Jahr abgeschlossen werden. Wer mitten im Jahr beginnt, setzt den Buchungsmonat in der Buchungssteuerung auf Januar und schließt die leeren Monate nacheinander ab.

Empfohlene Reihenfolge beim Einrichten: Kostenstellen anlegen, Ansätze und Monatswerte in der Kostenstellenplanung erfassen, danach in der Buchungssteuerung die Planung aktivieren. Ab dann ist der Haushaltsansatz fix und ändert sich nur durch Ansatzumbuchung. Eine Kostenstelle, die erst nach der Aktivierung angelegt wird, erhält ihren Ansatz über eine Ansatzumbuchung (z. B. aus einer Kostenstelle „Haushaltsreserve“). Einnahmen (Rente, PV-Entgelt, Orgelspiel, Zinsen) legen Sie als Kostenstelle der Art „Einnahme“ an, planen sie unter „Planung → Einnahmenplanung“ und geben sie per Ansatzumbuchung an Kostenstellen mit Plan weiter; bei „nur nach Ist verfügbar“ (z. B. Zinsen) ist nur die bereits gebuchte Einnahme umbuchbar.

Hinweis: Der Kontostand ist Anfangssaldo plus Bewegung. Die Anfangssalden pflegen Sie im Menü „Stammdaten → Kontenanfangssalden“. Sie sind editierbar, solange das Konto kein Vorjahr hat und der Januar nicht abgeschlossen ist.

## Einrichten und Starten

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m meine_kasse.main
```

Die Datenbank liegt standardmäßig unter `%LOCALAPPDATA%\MeineKasse\meine_kasse.sqlite`. Mit der Umgebungsvariable `MEINE_KASSE_DB` kann ein anderer Pfad gesetzt werden. Beim Start wird das Schema automatisch migriert.

## Installationspaket für den Testbetrieb (ohne Entwicklungsumgebung)

Das Paket ist ein Ordner mit `MeineKasse.exe` (PyInstaller). Auf dem Testrechner sind **kein Python und keine Installation** nötig.

Bauen (einmalig `pip install -e ".[dev,build]"`):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Ergebnis: `dist\MeineKasse\` und `dist\MeineKasse-<Version>-win64.zip` (ca. 110 MB, Bauzeit einige Minuten). Das Skript führt am Ende automatisch einen **Smoke-Test** aus: Selbsttest (`MeineKasse.exe --selbsttest`: Anwender mit Argon2, Stammdaten, Buchung, Abschluss mit Signatur, Datensicherung in einer temporären Datenbank) und einen Start der Oberfläche mit Migrationsprüfung.

Auf dem Testrechner:

1. ZIP entpacken und den **ganzen Ordner** `MeineKasse` an einen beliebigen Ort kopieren (z. B. `C:\Programme\MeineKasse` oder `C:\Tools\MeineKasse`).
2. `MeineKasse.exe` starten. Beim ersten Start nach dem Kopieren prüft Windows die Dateien, das kann 20 bis 40 Sekunden dauern. Die EXE ist nicht signiert, SmartScreen fragt ggf. nach („Weitere Informationen“ → „Trotzdem ausführen“).
3. Daten liegen **nicht** im Programmordner, sondern in `%LOCALAPPDATA%\MeineKasse` (Datenbank `meine_kasse.sqlite`, Protokoll `logs\meine_kasse.log`). Ein Update ersetzt nur den Programmordner. Mit der Umgebungsvariable `MEINE_KASSE_DB` lässt sich eine andere Datenbankdatei verwenden, z. B. für Tests.
4. Datensicherung im Programm: Datei → Datensicherung erstellen. Vor jedem Update sichern.

Eine ausführliche Anleitung für Tester liegt als `LIESMICH.txt` im Paket (Quelle: `packaging\LIESMICH.txt`).

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
