# Meine Kasse – Analyse Testergebnisse 1

Grundlage: `Testergebnisse_1.docx`, Ist-Stand des Codes und [Architekturvorgabe](./ARCHITEKTURVORGABE.md) Version 3. Die daraus folgenden Regeln stehen dort in 2.11–2.14.

## 1. Kurzfazit

- Der **Kern bleibt tragfähig** (Schichten, Cent-Beträge, Transaktionen, Abschlüsse, Signaturen).
- **Drei Hinweise ändern Fachlogik** und sind der Kern der Arbeit: Plan-Ist nach Entstehungsdatum (Abschnitt B1), Rückstellungen (B2) und Cash-Management (B3).
- Alles Übrige (Bedienung, Tabellen, PDF, Auswertungen) ist **zusätzliche Funktionalität** ohne Eingriff in die Buchungsregeln, aber mit einer wiederverwendbaren Grundlage (Tabellenkomponente, Anwendereinstellungen).
- **Auswertungen** waren bisher ausdrücklich nicht im Umfang (Architekturvorgabe 1 und 7). Sie sind jetzt Teil davon, ein Umfangswechsel.

## 2. Ist-Stand, der die Änderungen beeinflusst

| Befund im Code | Folge |
| --- | --- |
| `effects_of` schreibt Ist nach `fiscal_year`/`fiscal_month`, also dem **Buchungsdatum** (`booking_rules.py`) | Umstellung auf Entstehungsdatum nötig (B1) |
| `reserve_actual_cents` existiert, wird aber **nie befüllt**; Rückstellung ist heute nur ein manuelles Planfeld und manuelle Überträge | Rückstellungslogik ist Neubau, kein Umbau (B2) |
| `plan_mode` geht in die **Monatssignatur** ein (`closing_rules.py`) | Spalte darf nicht entfernt werden, sonst werden bereits abgeschlossene Monate ungültig |
| Alle Tabellen sind `QTableWidget` ohne Filter/Sortierung; Auswahlen sind einfache `QComboBox` | Gemeinsame Komponenten statt Einzellösungen (A3, C1–C3) |
| Es gibt keine Anwendereinstellungen und keine Ausgabe-/Dokumentenablage | Neue Tabellen `user_settings`, `documents`, `report_definitions` |
| Die Datensicherung kopiert nur die Datenbank | muss um das Dokumentenverzeichnis erweitert werden |

## 3. Bewertung je Hinweis

### A. Buchungen

| # | Hinweis | Vorteil | Nachteil / Risiko | Empfehlung |
| --- | --- | --- | --- | --- |
| A1 | Zuletzt benutztes Buchungsdatum vortragen; anderer Monat → 1. des Buchungsmonats | schnelle Serienerfassung | gering; Vorgabe bleibt im Fenster ±1 Monat | umsetzen; Wert nur im Dialog/Sitzung halten |
| A2 | Datum per Tag eingeben; Entstehungsdatum ebenso, sonst frei | deutlich weniger Tastendrücke | Mehrdeutigkeit „15“ vs. „15.1.“ | **ein** Textfeld mit Parser (Tag, `T.M.`, `T.M.JJJJ`), Monat/Jahr aus Buchungsmonat; Parser mit Tests. Fenster ±1 Monat bleibt über volles Datum erreichbar |
| A3 | Kostenstelle per Textteil filtern („Geb“ → „Volksbank Gebühr“) | schnelleres Finden, auch bei vielen Stellen | ein neues Widget nötig | `FilterComboBox` (Teilstring in Name **und** Nummer); gleiches Widget für alle Auswahlen (C2) |
| A4 | Sortierreihenfolge der Buchungsliste umschaltbar, pro Anwender gespeichert | neueste Buchung oben | benötigt Ablage der Einstellung | als Sonderfall der allgemeinen Spaltensortierung (C3) lösen, Ablage in `user_settings` (nicht `QSettings`, da dort pro Windows-Benutzer statt pro Anwender) |

### B. Planung, Rückstellung, Cash-Management

**B1 Plan nach Entstehungsdatum.** Die Ist-Zuordnung zum Plan folgt dem Entstehungsdatum, der Abschluss dem Buchungsdatum (Architekturvorgabe 2.11).

| Vorteil | Nachteil / Risiko |
| --- | --- |
| Plan-Ist entspricht der Fachlichkeit (Kosten fallen in dem Monat an, in dem sie entstanden sind) | Zwei Zeitachsen müssen klar getrennt bleiben (Konten ↔ Kostenstellen) |
| Monatssignatur bleibt stabil, da sie über die Buchungsperiode läuft | Ist eines **geschlossenen** Planmonats ändert sich nachträglich; das ist gewollt, aber die Monatsansicht muss das kennzeichnen |
| Vorjahr-Regel verhindert Buchungen in nicht existierende oder abgeschlossene Jahre | Hinweisdialog nötig (Kostenstelle, Jahr, Grund); Storno-Sonderfall (Entstehungsdatum des Stornos, 2.11 Nr. 4) |

Betroffen: `effects_of`, `rebuild_projections`, Abschlussprüfung (`projection_mismatches`), Ansatzsperre (Jahr der Planperiode), Buchungsmaske (Anzeige Restansatz zum Planjahr). Bestehende Testdaten (Januar/Februar) werden per Neuaufbau umgerechnet; weichen Entstehungs- und Buchungsmonat nicht ab, ändert sich nichts.

**B2 Rückstellungen.**

| Vorteil | Nachteil / Risiko |
| --- | --- |
| Virtuelles Konto je Kostenstelle: kein Eingriff in Konten/Kontrollsumme, keine Synchronisation | Rückstellung ist nicht direkt bebuchbar; Korrektur nur über Plan (manuelle Monatswerte) |
| Berechnung nach **Monatssummen** statt Buchungsreihenfolge: deterministisch und neu aufbaubar (Entwicklungsregel 3.11) | Eine Buchung im Frühjahr kann die Entlastung späterer Monate verändern (Kettenberechnung über das Jahr) |
| „Vorziehen“ der Zuführung vor die Zahlung plus „nie negativ“ ergibt einfache, prüfbare Invarianten (Summe bleibt, Bestand ≥ 0) | Die Zuführungen späterer Monate werden dafür geringer; bleibt ein Fehlbetrag (z. B. durch gesperrte Monate), nur Hinweis |
| Ansatzsperre bleibt unverändert; Rückstellung teilt den Ansatz nur auf | Vorzeichenkonvention weicht optisch von 2.2 ab (siehe Entscheidung E1) |

Das Verfahren der Verteilung (Beispiel, so umgesetzt): Versicherung, Jahresansatz 1.200 €, Planwerte März 600 €, September 600 €, Vortrag 0.

1. Gleichmäßig: 100 €/Monat. Bestand im März 300 € < 600 € → Fehlbetrag 300 €.
2. Januar–März werden um je 100 € erhöht (je 200 €), die Monate nach dem März erhalten dafür weniger. Bestand im März 600 €, nach der Zahlung 0.
3. Im September fehlen danach noch 200 €: April–September erhalten wieder je 100 €, Oktober–Dezember 0 €. Bestand im September 600 € (kumuliert 1.200 € abzüglich 600 € aus dem März), nach der Zahlung 0. Summe der Zuführungen 1.200 € = Jahresansatz.

Die Verschiebung ist deterministisch: Eine Lücke wird in den freien Monaten seit der letzten Lücke ausgeglichen, die Gegenbuchung erfolgt gleichmäßig aus den Monaten danach. Manuell gesetzte und abgeschlossene Monate werden nie angefasst. Das Verfahren ist in `tests/unit/test_reserve_rules.py` festgeschrieben, einschließlich Zufallsprüfungen (keine Lücke, wenn die geplanten Zahlungen den Ansatz nicht übersteigen).

**Wegfall der Planungsart und der Quartalsverteilung:** Sinnvoll, weil Gleichmäßig und Rückstellung jetzt feste Abläufe sind. Nachteil: Die Spalte `plan_mode` muss wegen der Signatur bleiben (nur nicht mehr bedient). Die Quartalsmaske (`quarter_amounts_dialog.py`) und die Modus-Auswahl im Planungsdialog entfallen.

**B3 Cash-Management.**

| Vorteil | Nachteil / Risiko |
| --- | --- |
| Kontenabgleich mit Kontoauszug prüft Vollständigkeit und Beträge sofort beim Öffnen | Erwarteter Kontostand ist Handeingabe; muss je Monat gespeichert werden (E3) |
| Zahlungskonto minus geplante Ausgaben zeigt den frei verfügbaren Rest | „Geplante Ausgaben“ braucht einen Horizont (E4) |
| Betriebsmittel ↔ Rückstellungsbestand dient als Kontrollgröße | Funktioniert nur, wenn die Betriebsmittelbuchungen manuell korrekt erfolgen; Differenz ist Hinweis, keine Sperre |

Rollen (`cash_role`) werden am Konto gekennzeichnet; je Rolle höchstens ein Konto (Teilindex bzw. Prüfung im Service).

### C. Allgemein

| # | Hinweis | Vorteil | Nachteil / Risiko | Empfehlung |
| --- | --- | --- | --- | --- |
| C1 | Ja/Nein statt Yes/No | einheitlich deutsch | – | `QTranslator` mit `qtbase_de` global laden (wirkt auch auf alle Standarddialoge); `.qm`-Dateien in PyInstaller-Paket aufnehmen und im Selbsttest prüfen |
| C2 | Auswahlen immer per Filter | konsistente Bedienung | – | ein Widget `FilterComboBox`, Verbot eigener Combobox-Logik in Dialogen |
| C3 | Spaltensuche und Sortierung je Tabelle | schnelle Orientierung | `QTableWidget` sortiert Text; Beträge/Datum würden falsch sortiert | gemeinsame `DataTable` auf `QSortFilterProxyModel`; Sortierung nach Rohwerten (Cent, Datum) |
| C4 | PDF „wie dargestellt“ | einfache Ausgabe | Dateiname, Ablage, Zeichensatz, Seitenumbruch | Port in Application, Renderer in Infrastructure. `reportlab`: volle Kontrolle (Seitenzahl, Kopfwiederholung, Gruppen), eine neue Abhängigkeit. Qt-PDF: keine neue Abhängigkeit, weniger Kontrolle. **Empfehlung `reportlab`**, da Auswertungen Gruppen und Summen brauchen |
| C5 | Dokumentenarchiv | Ausdrucke wiederauffindbar, nachvollziehbar (Hash) | PDFs enthalten Finanzdaten; Sicherung und Datenschutz | Verzeichnis unter `%LOCALAPPDATA%\MeineKasse\Dokumente`, Index in `documents`, Sicherung erweitern. Das „eigene Ausgabeverzeichnis“ und das Archiv sind **dasselbe** |
| C6 | Buchungen je Konto/Kostenstelle einschränken | gezielte Kontrolle | Spaltenfilter reicht nicht (Buchung hat zwei Stellen) | Filter als Abfrageparameter im Repository, zusätzlich zum Monat |
| C7 | Auswertungsdialog mit speicherbaren Spalten, Filtern, Sortierung, Gruppen, Summen | sehr flexibel, ersetzt künftige Einzelberichte | größtes Teilprojekt; Gefahr falscher Summen (siehe unten) | in Phase 7, mit festen Datenquellen und Whitelist-Filtern |

**Wichtiger Befund zu den Auswertungen:** Die genannten Spalten haben unterschiedliche Zeilenbedeutung. Soll/Haben gehören zu einer Buchung, Ansatz, Restansatz, Monatsplan und Rückstellung zu Kostenstelle × Jahr bzw. Monat. In **einer** Tabelle gemischt würde z. B. der Jahresansatz je Buchung mehrfach summiert. Deshalb gibt es feste **Datenquellen** (Buchungen, Plan/Ist, Konten) und je Spalte die Kennzeichnung `ADDITIVE`/`NON_ADDITIVE`. Gesamtsummen summieren nur `ADDITIVE`-Spalten („nur Beträge“ reicht nicht, ein Ansatz ist auch ein Betrag).

**Ergänzende Spalten (Antwort auf „Fehlen noch welche?“):** Buchungsdatum, Entstehungsdatum, Buchungsart, Kostenstellennummer, Kontonummer und -art, Gegenkonto, Text und Händler, Status (offen/abgeschlossen, Storno), Anwender, Ist-Bewegung, Abweichung zum Monatsplan, Basisansatz, Ansatzumbuchungen, verteilter und unverteilter Ansatz, Zuführung, Entlastung, Rückstellungsbestand, Anfangssaldo, Saldo, erwarteter Kontostand und Differenz.

**Klarstellung zu C7 (alles abbilden oder Spezialfunktionen?):** Empfohlen und festgelegt ist ein **Mittelweg**. Es gibt eine allgemeine Auswertung auf drei Datenquellen mit erweiterbarem Spaltenkatalog. Die meisten Fragen („Was habe ich im Februar bei Kostenstelle X ausgegeben?“) sind dann Spaltenwahl, Filter und Gruppierung und brauchen keinen neuen Code. Spezialfunktionen gibt es nur dort, wo eine echte Berechnung dahintersteht (Cash-Management, Abschlussprüfung).

| Weg | Vorteil | Nachteil |
| --- | --- | --- |
| Alles in einer Auswertung | maximale Flexibilität | Summenfehler bei gemischten Zeilenarten, überladene Bedienung, nie fertig |
| Nur Einzelberichte | einfach, korrekt | jede neue Frage kostet Entwicklung |
| **Datenquellen + Spaltenkatalog (gewählt)** | neue Frage = oft nur Katalogzeile; Summen bleiben korrekt | Datenquellen müssen vorab sauber definiert werden |

Vorgehen: Die Auswertung startet mit den Spalten aus Abschnitt 3 und wird bei konkretem Bedarf erweitert. Daher gehört sie ans Ende (Phase 7), wenn der Bedarf aus der Praxis feststeht.

## 4. Entscheidungen (getroffen)

| # | Frage | Entscheidung |
| --- | --- | --- |
| E1 | Rückstellung: Soll = Bildung, Haben = Entlastung | wie vorgeschlagen: Sicht des Rückstellungskontos übernehmen, mit „Bildung/Entlastung“ beschriften |
| E2 | Planjahr ohne Plan oder abgeschlossen: Hinweis | Hinweisdialog pro Buchung (Empfehlung, keine Gegenaussage) |
| E3 | Erwarteter Kontostand | je Konto und Monat, mit Fortschreibung des letzten Werts |
| E4 | „Geplante Ausgaben“ im Zahlungskonto | zwei Spalten: offen im aktuellen Monat, offen bis Jahresende |
| E5 | Kostenstellenart „ohne Plan“ | bleibt bestehen, für nicht planbare Stellen wie durchlaufende Posten |
| E6 | Verteilung des Ansatzes | gesamter Jahresansatz wird verteilt, direkt geplante Zahlungen entlasten |
| E7 | PDF-Bibliothek | `reportlab` |

## 5. Realisierungsablauf

Reihenfolge nach Abhängigkeiten. Jede Phase endet mit grünen Tests (`pytest`, `ruff`, `mypy`) und Abnahme nach Entwicklungsregeln 8. Aufwand grob: S = Tage, M = ca. 1–2 Wochen, L = mehrere Wochen.

```text
Phase 0  Entscheidungen E1–E7 (erledigt)
   |
   +--> Phase 1  Bedienkomfort (ohne Fachlogik)         S
   |       |
   |       v
   |    Phase 2  Tabellenkomponente + Anwendereinstellungen   M
   |       |
   v       |
Phase 3  Planperiode (Entstehungsdatum)                 M
   |       |
   v       |
Phase 4  Rückstellungen                                 L
   |       |
   v       v
Phase 5  Cash-Management          Phase 6  PDF + Dokumentenarchiv   M
   (braucht 4)                        (braucht 2)
                                          |
                                          v
                                   Phase 7  Auswertungen (braucht 2, 4, 6)   L
```

Phase 1 und 3 sind unabhängig und können parallel laufen. Phase 5 und 6 ebenfalls.

| Phase | Inhalt | Migration | Wesentliche Tests |
| --- | --- | --- | --- |
| 0 | Entscheidungen E1–E7 (erledigt); Architekturvorgabe auf „festgelegt“ gesetzt | – | – |
| 1 | `qtbase_de` (Ja/Nein), `FilterComboBox` in Buchungs- und Planungsdialog, Datumsvortrag, Tag-/Datumsparser, Standardknopf „Speichern“ im Planungsdialog, Filter Konto/Kostenstelle in der Buchungsliste | – | Parser (Tag, Teildatum, ungültig), Standarddatum (anderer Monat), Repository-Filter |
| 2 (erledigt) | `DataTable` (Spaltenfilter, Sortierung nach Rohwerten) in Buchungsliste, Stammdatenlisten und Wiedereröffnungshistorie, `user_settings` samt Service, persistente Sortierung. Monatsraster und Anfangssalden bleiben ohne Filter/Sortierung (Eingabetabellen) | 0004 `user_settings` | Sortierung Beträge/Datum, Persistenz je Anwender, Filter kombinierbar |
| 3 (erledigt) | `effects_of`/`rebuild_projections` auf Planperiode, Vorjahr-Regel samt Hinweisdialog, Storno-Regel, Abschlussprüfung auf Planperiode, Anzeige Planjahr in der Maske, Spalte „Entstehung“ in der Buchungsliste | 0005 (einmaliger Neuaufbau der Ist-Werte) | Entstehung im Vorjahr (Plan vorhanden/fehlt/abgeschlossen), geschlossener Planmonat im offenen Jahr, Änderung des Entstehungsdatums, Rebuild identisch zur Fortschreibung, Migration |
| 4 (erledigt) | `reserve_rules` (Domain, reine Funktionen), maschinelle Verteilung mit Live-Vorschau im Planungsdialog, `reserve_is_manual`, Entlastung in `monthly_actuals` bei jeder Buchung, Hinweis bei Unterdeckung, Jahresvortrag über mehrere Jahre, Prüfung beim Abschluss, Neuberechnung beim Start, Wegfall Planungsart/Quartale, „Speichern“ als Standardknopf | 0006 `reserve_is_manual` (Altbestand gilt als manuell) | Beispiel aus Abschnitt 3, Vortrag, nie negativ, geschlossene/manuelle Monate, Erstattung, Reihenfolgeunabhängigkeit, Neuaufbau, Abschlussprüfung, Migration |
| 5 | `cash_role` am Konto, `account_balance_checks`, Cash-Management-Dialog | 0006 | Kontenabgleich mit Differenz, Rollen eindeutig, Zahlungskonto-Rest, Betriebsmittel ↔ Rückstellungsbestand |
| 6 | PDF-Port und Renderer, Dateinamenbildung, `documents`, Archivdialog, Sicherung inkl. Dokumente, Selbsttest | 0007 `documents` | Dateiname (40 Zeichen, unzulässige Zeichen), Hash, Sicherung enthält Dokumente, Selbsttest im gepackten Programm |
| 7 | Datenquellen, Spaltenkatalog mit `ADDITIVE`/`NON_ADDITIVE`, Filterbedingungen (Whitelist), Gruppierung mit Zwischensummen, „nur Summen“ je Ebene, Kopfsumme, `report_definitions`, Auswertungsdialog, PDF-Ausgabe | 0008 `report_definitions` | Summen je Datenquelle, keine Mehrfachzählung von Ansatz/Restansatz, Gruppensummen, gespeicherte Auswertung lädt identisch, ungültige Spalten/Operatoren werden abgelehnt |

### Reihenfolge der Nutzbarkeit

1. **Nach Phase 1–2:** Die täglich gespürten Reibungspunkte der Tests (Datum, Auswahl, Sortierung) sind behoben.
2. **Nach Phase 3–4:** Planung stimmt fachlich mit Ihrer Beschreibung überein. Das ist der wichtigste Meilenstein, da Februar-Daten danach neu aufgebaut werden und ab hier der Weg für weitere Monate sicher ist.
3. **Nach Phase 5:** Liquiditätsüberblick.
4. **Nach Phase 6–7:** Ausgaben und Auswertungen.

### Hinweise zum Betrieb

- Vor Phase 3 und 4 eine **Datensicherung** der Testdatenbank anlegen; der Neuaufbau (`rebuild_projections`) erlaubt anschließend eine Kontrolle gegen die vorherigen Werte.
- Jede Phase wird als eigene, getestete Alembic-Migration ausgeliefert; das Migrationsverzeichnis wird von `packaging\meine_kasse.spec` vollständig mitgeliefert.
