# Meine Kasse – Architekturvorgabe

Version 2 – Grundlage: Dokument „PDVM Meine Kasse“ und Klarstellung zu Negativbeträgen.

## 1. Ziel und Geltungsbereich

Meine Kasse ist eine deutschsprachige Desktop-Anwendung (Python, integrierte SQLite) für eine einfache Buchhaltung auf Kostenstellen und Konten (Bank oder Anlagen).

Umfang des ersten Ausbaustands:

- Anmeldung mit lokal verwalteten Anwendern (ohne Berechtigungskonzept), danach Hauptmenü
- Stammdaten und Steuerung: Kostenstellen, Konten, Anwender, Buchungssteuerung
- Buchungen mit Soll/Haben, positiven **und negativen** Beträgen
- Planung je Kostenstelle (Jahressumme, Monatswerte, Rückstellungen)
- Soll-/Ist-Abgleich direkt bei jeder Buchung mit **Sperre bei Überschreitung des Ansatzes**
- Ansatzumbuchungen zwischen Kostenstellen
- Monats- und Jahresabschluss mit Signaturen

Nicht Bestandteil: Auswertungen (folgen später), Fremdwährungen (nur €), Berechtigungsstufen, Bankanbindung.

## 2. Fachliche Festlegungen

### 2.1 Beträge, Vorzeichen, Soll/Haben

Das ist die zentrale Regel des Systems und ersetzt jede frühere Fassung.

| Thema | Festlegung |
| --- | --- |
| Vorzeichen | Beträge sind **vorzeichenbehaftet**. Positive und negative Beträge sind zulässig. |
| Kein Seitentausch | Ein negativer Betrag wird **niemals** durch Vertauschen von Soll und Haben in einen positiven Betrag umgewandelt. Was erfasst wurde, bleibt unverändert gespeichert und auswertbar. |
| Genau eine Seite | Ein Buchungssatz hat genau einen Betrag, entweder im Soll oder im Haben. Das jeweils andere Feld ist leer. |
| Betrag 0 | In der Maske sind bei Betrag 0 beide Felder bedienbar. Sobald in einem Feld ein Betrag ≠ 0 steht, ist das andere gesperrt. Gespeichert werden kann nur ein Betrag ≠ 0. |
| Währung | Ausschließlich Euro. Anzeige immer mit €, z. B. `1.234,56 €`. |
| Speicherung | Ganzzahlige Cent mit Vorzeichen (`INTEGER`), Verarbeitung als `Decimal`. Niemals `float`. |
| Prozentwerte | Mit mindestens 3 Nachkommastellen gespeichert und angezeigt (`Decimal`). |
| Prozentuale Aufteilung | Teilbeträge behalten das Vorzeichen des Gesamtbetrags. Rundungsdifferenzen (in Cent) werden einem definierten Teilbetrag zugeschlagen, sodass die Summe immer dem Gesamtbetrag entspricht. |

### 2.2 Buchungsrichtung: Soll und Haben bei Konto und Kostenstelle

Konten und Kostenstellen verwenden Soll und Haben mit **derselben Bedeutung**, nämlich in der Sicht des Kontoauszugs:

- **Soll** = Abfluss bzw. Verbrauch (Ausgabe)
- **Haben** = Zufluss bzw. Verfügbares (Einnahme, Erstattung, Ansatz)
- **Saldo = Haben − Soll.** Beim Konto ist das der Kontostand, bei der Kostenstelle der Haushaltsrest. Der Ansatz ist der Haben-Anteil der Kostenstelle und wird getrennt von den Ist-Buchungen geführt (siehe 2.7).

Grundlage ist die **Erfassungsseite (`entry_side`)**: `DEBIT` (Soll) oder `CREDIT` (Haben), also die Seite, in der der Anwender den Betrag eingibt.

| Buchungsart | Wirkung der Erfassungsseite |
| --- | --- |
| Kostenstelle → Konto (Ist-Buchung) | **Gleichgerichtet:** Kostenstelle und Konto werden auf derselben Seite gebucht. Es gibt keine Umkehr und keine Gegenseite. |
| Konto → Konto, Ansatz Kostenstelle → Ansatz Kostenstelle | **Gegenläufig:** Die erste (führende) Stelle wird auf der Erfassungsseite gebucht, die zweite auf der gegenüberliegenden. Das ist fachlich zwingend, weil die Quelle abgibt und das Ziel erhält. |

Es gibt keine Sachkonten und keine doppelte Buchführung im klassischen Sinn („Kostenstelle an Bank“ entfällt). Sachkonten wären nur für Bilanz und GuV nötig. Eine Kategorie kann später als Merkmal ergänzt werden.

Wirkung eines Betrags `b` (mit Vorzeichen) auf jede Stelle, die auf der betreffenden Seite gebucht wird:

| Erfassungsseite | Soll-Summe | Haben-Summe | Nettobewegung (Soll − Haben) |
| ---             | ---        | ---         | ---                          | 
| Soll, `b`       | + b        | –           | + b                          |
| Haben, `b`      | –          | + b         | − b                          |

Beispiele:

- Ausgabe 50 € für Lebensmittel, bezahlt vom Girokonto: Soll 50 € bei der Kostenstelle **und** Soll 50 € beim Girokonto. Kontostand und Haushaltsrest sinken um 50 €.
- Erstattung 20 €: Haben 20 € bei beiden Stellen. Wird sie als Soll −20 € erfasst, bleibt das ebenfalls so gespeichert (kein Seitentausch). Die Wirkung auf Saldo und Haushaltsrest ist gleich, die Erfassung bleibt unterscheidbar.

**Kontrollsumme:** Die Summe der Kontenbewegungen aus Ist-Buchungen (Haben − Soll) muss der Summe der Ist-Bewegungen aller Kostenstellen (Haben − Soll) entsprechen. Umbuchungen zwischen Konten ergeben in Summe 0. Diese Prüfung ersetzt die Soll = Haben-Kontrolle der Doppik.

### 2.3 Auswirkungen auf Planung und Abgleich

| Bereich | Festlegung | Status |
| --- | --- | --- |
| Soll/Haben getrennt führen | Die Ist-Werte führen Soll-Summe und Haben-Summe **getrennt und mit Vorzeichen**. Beide können negativ sein. Die echte Bewegung ist `Soll − Haben`. | festgelegt |
| Haushaltsrestbetrag | `Jahresansatz − Ist-Bewegung (Soll − Haben)`. Negative Buchungen erhöhen den Restbetrag, Buchungen mit Haben-Seite ebenfalls. | festgelegt |
| Monatsabgleich | Der Plan-Ansatz des Monats wird mit der Ist-Bewegung des Monats verglichen, jeweils vorzeichenrichtig. | festgelegt |
| Rückstellung ist | Entsteht aus Buchungen auf Rückstellungsstellen/-konten nach derselben Vorzeichenlogik. | festgelegt |
| Storno/Korrektur | Eine Buchung wird durch eine **Minusbuchung auf derselben Seite** (gleiche Stellen, Betrag mit umgekehrtem Vorzeichen) korrigiert, verknüpft über `reversal_of_booking_id`. Das entspricht dem klassischen Rotstorno und verändert die Seite nicht. | festgelegt |
| Vorzeichen von Planwerten | Planwerte (Jahresansatz, Monatsplan, Rückstellungsplan, Übertrag) werden in Soll-Richtung geführt, also mit **derselben Konvention** wie Ist-Werte. Der Jahresansatz ist immer ≥ 0. Plan und Ist sind damit ohne Umrechnung vergleichbar. | festgelegt |
| Überschreitung | Eine Überschreitung des Jahresansatzes **sperrt** die Buchung (siehe 2.7). | festgelegt |
| Einnahmen/Ausgaben | Kostenstellen und Konten werden **nicht** als Einnahme- oder Ausgabeobjekt gekennzeichnet. Einnahmen und Erstattungen sind Haben- bzw. Minusbuchungen und entlasten die Kostenstelle über die Vorzeichenlogik. | festgelegt |

### 2.4 Buchungsarten

| Art (`booking_type`) | Führende Stelle | Zweite Stelle | Seite der zweiten Stelle | Wirkung |
| --- | --- | --- | --- | --- |
| Kostenstelle → Konto (`COST_CENTER_TO_ACCOUNT`) | Kostenstelle | Konto | gleich | Ist der Kostenstelle und Saldo des Kontos; unterliegt der Ansatzsperre |
| Konto → Konto (`ACCOUNT_TO_ACCOUNT`) | Konto | Konto | gegenläufig | nur Kontosalden, keine Planwirkung |
| Ansatz Kostenstelle → Ansatz Kostenstelle (`BUDGET_TRANSFER`) | Kostenstelle | Kostenstelle | gegenläufig | nur Jahresansatz beider Kostenstellen; kein Ist, keine Konten |

Zulässige Kombinationen werden zentral je Buchungsart definiert und validiert. Die Kontoart (Giro, Spar, Anlage, Rückstellung) wird nicht mit der Planposition „Rückstellung“ vermischt.

Die frühere Art „Kostenstelle an Kostenstelle“ als Ist-Umbuchung entfällt. Falsch zugeordnete Ist-Buchungen werden durch Minusbuchung und neue Buchung korrigiert (siehe 2.3).

### 2.5 Perioden und Abschlüsse

- Eine Buchung ist erst mit dem Abschluss ihres Monats unveränderbar („gebucht“). Bis dahin darf sie geändert werden; jede Änderung wird protokolliert.
- Buchbar sind nur der aktuelle Buchungsmonat sowie ein Monat davor und danach.
- Monatsabschluss: speichert Abschlussdatum und Signatur. Jahresabschluss: setzt voraus, dass alle Monate abgeschlossen sind.
- Offene (frei) und abgeschlossene (fixe) Monate sind in Dialogen und Auswertungen erkennbar.
- Korrekturen in abgeschlossenen Zeiträumen erfolgen nur durch Minusbuchung (siehe 2.3) in einem offenen Zeitraum.

### 2.6 Salden

Konten- und Kostenstellensalden sind aus den Buchungen berechenbar. Gespeicherte Werte (Plan-Ist-Fortschreibung) sind transaktional geführte Projektionen und jederzeit aus den Buchungen neu aufbaubar.

### 2.7 Ansatzsperre und Ansatzumbuchung

**Begriffe**

| Begriff | Berechnung |
| --- | --- |
| Basisansatz | Jahresansatz, der vor Aktivierung der Planung festgelegt wird |
| Ansatzumbuchungen | Summe der `BUDGET_TRANSFER`-Wirkungen auf die Kostenstelle (mit Vorzeichen) |
| Jahresansatz (wirksam) | Basisansatz + Ansatzumbuchungen |
| Ist-Bewegung | Soll − Haben aus Ist-Buchungen (ohne Ansatzumbuchungen) |
| Haushaltsrest | Jahresansatz (wirksam) − Ist-Bewegung |
| Verteilter Ansatz | Summe der Monatsplanwerte |

**Sperrregeln** (gelten bei aktivierter Planung für Kostenstellen der Art `STANDARD`; `WITHOUT_PLAN` wird nicht geprüft)

1. Eine Ist-Buchung wird abgelehnt, wenn sie die Ist-Bewegung erhöht und der Haushaltsrest danach kleiner als 0 wäre. Buchungen mit entlastender Wirkung (Haben, Minusbuchungen) werden nie gesperrt.
2. Eine Ansatzumbuchung wird abgelehnt, wenn bei der abgebenden Kostenstelle danach der Jahresansatz kleiner als 0, kleiner als die Ist-Bewegung oder kleiner als der verteilte Ansatz wäre.
3. Ansatzumbuchungen sind nur bei aktivierter Planung, zwischen zwei verschiedenen `STANDARD`-Kostenstellen und in einem offenen Zeitraum möglich.
4. Die Fehlermeldung nennt Haushaltsrest und fehlenden Betrag und verweist auf die Ansatzumbuchung. Die Buchungsmaske bietet dafür direkt den Einstieg an.
5. Der Monatsplan sperrt nicht, sondern wird nur als Abweichung angezeigt. Das ist festgelegt, da bei unregelmäßigen Ausgaben und Rückstellungen eine monatliche Sperre unpraktisch wäre.
6. Die Prüfung und die Buchung erfolgen in derselben Transaktion (mit sofortiger Schreibsperre, `BEGIN IMMEDIATE`), damit keine Überschreitung durch parallele Vorgänge entsteht.

**Wirkung einer Ansatzumbuchung** nach der Regel aus 2.2 (Soll = Abgabe, Haben = Zugang, zweite Stelle gegenläufig):

| Erfassungsseite | Führende Kostenstelle | Zweite Kostenstelle |
| --- | --- | --- |
| Soll, `b` | Ansatz − b (gibt ab) | Ansatz + b (erhält) |
| Haben, `b` | Ansatz + b (erhält) | Ansatz − b (gibt ab) |

Die Summe aller Ansätze bleibt dadurch unverändert. Ein negativer Betrag kehrt die Wirkung um, ohne die Seite zu tauschen. Ist-Werte, Konten und Salden werden nicht berührt.

### 2.8 Planänderung: in der Planung oder per Buchung

**Festgelegt:** Die Höhe des Ansatzes wird nur per Buchung geändert, die Verteilung innerhalb des Ansatzes in der Planung.

| Änderung | Ort | Begründung |
| --- | --- | --- |
| Erstmalige Festlegung des Jahresansatzes | Planung, solange die Planung nicht aktiviert ist | Danach ist der Haushaltsansatz fix |
| Höhe des Jahresansatzes einer Kostenstelle | nur über Ansatzumbuchung | Gesamthaushalt bleibt konstant, Änderung ist belegt, datiert und signiert |
| Verteilung auf Monate, Quartale, unregelmäßige Beträge und Rückstellungen innerhalb des Jahresansatzes | Planung (Planungsdialog), ohne Buchung | Gesamtsumme ändert sich nicht, Vorgang ist reine Planungsarbeit |

Regeln dazu:

- Die Summe der Monatsplanwerte darf den wirksamen Jahresansatz nicht überschreiten. Die Differenz ist der unverteilte Ansatz.
- Die empfangende Kostenstelle verteilt den erhaltenen Ansatz anschließend selbst in der Planung. Die abgebende Kostenstelle kann nur unverteilten Ansatz abgeben oder muss ihre Monatsplanung zuvor verringern.
- Planänderungen sind nur in offenen Monaten möglich und werden im Audit-Protokoll festgehalten.
- Die Signatur eines Monatsabschlusses umfasst auch die Ansatzumbuchungen und Monatsplanwerte des Monats.

Gegenüber „alles über Buchungen“ erzeugt dieser Weg keine Buchungen ohne fachlichen Wert für reine Umverteilungen. Gegenüber „alles in der Planung“ bleibt jede Änderung der Ansatzhöhe nachvollziehbar.

### 2.9 Haushaltsreserve

Zusätzliche Mittel (z. B. höheres Einkommen) werden über eine normale Kostenstelle „Haushaltsreserve“ der Art `STANDARD` abgebildet. Sie erhält ihren Ansatz wie jede andere Kostenstelle, und daraus wird per Ansatzumbuchung auf andere Kostenstellen verteilt. Es gibt keine Ansatzänderung ohne Gegenstelle und keine Sonderart für diese Kostenstelle.

## 3. Systemarchitektur

```text
Desktop-Oberfläche
        |
        v
Anwendungsdienste (Use Cases, Transaktionen)
        |
        +--> Domain: Fachregeln, Werteobjekte
        |
        v
Repository-Schnittstellen
        |
        v
Zentraler Datenzugriff (SQLite)
```

### 3.1 Technologie

| Bereich | Festlegung |
| --- | --- |
| Sprache | Python 3.11 oder neuer |
| Oberfläche | PySide6 |
| Persistenz | SQLite über SQLAlchemy 2.x |
| Migrationen | Alembic |
| Passwort | Argon2id (`argon2-cffi`), nur Hash wird gespeichert |
| Tests | pytest |
| Auslieferung | PyInstaller |

### 3.2 Schichten

| Schicht | Aufgabe | Verboten |
| --- | --- | --- |
| `presentation` | Fenster, Dialoge, Formatierung, Fehleranzeige | SQL, Buchungsregeln |
| `application` | Anwendungsfälle, Transaktionsgrenzen | Qt-Objekte, ORM-Objekte nach außen |
| `domain` | Buchungs-, Planungs- und Abschlussregeln | UI- oder DB-Importe |
| `infrastructure` | Datenzugriff, Hashing, Migrationen | Fachregeln |

**Zentraler Datenzugriff:** Alle Datenbankzugriffe laufen über genau eine Infrastruktur-Komponente (Repositories mit gemeinsamer Unit of Work). Beim Wechsel der Datenbank wird nur diese angepasst.

### 3.3 Projektstruktur

```text
Meine Kasse/
  src/meine_kasse/
    application/
    domain/
    infrastructure/
      database/ (models, repositories, migrations)
      security/
    presentation/ (dialogs, view_models, widgets)
    bootstrap.py
    main.py
  tests/ (unit, integration)
  pyproject.toml
  alembic.ini
```

## 4. Datenmodell

### 4.1 Konventionen

- Jeder Datensatz hat eine `id` (GUID, Text) als Primärschlüssel und einen `name`. Der Inhalt von `name` wird je Tabelle festgelegt.
- Verbindungen erfolgen ausschließlich über die GUID.
- `created_at`, `updated_at` (UTC) in jeder Tabelle; Stammdaten zusätzlich `is_active`.
- Fremdschlüssel sind aktiviert (`PRAGMA foreign_keys = ON`).

### 4.2 Stammdaten und Steuerung

| Tabelle | Wesentliche Felder |
| --- | --- |
| `users` | id, name, last_name, first_name, address, password_hash, initial_password_hash, must_change_password, password_changed_at |
| `cost_centers` | id, name, number, valid_from, kind (`STANDARD` / `WITHOUT_PLAN`), notes |
| `accounts` | id, name, number, account_type (`CHECKING`, `SAVINGS`, `INVESTMENT`, `RESERVE`), bank_name, owner_name, iban |
| `booking_control` | id, is_active (genau ein aktiver Datensatz), planning_enabled, current_year, current_month, last_closed_year, last_closed_month |
| `period_closures` | id, year, month, closed_on, signature |
| `year_closures` | id, year, closed_on, signature |
| `closure_reopenings` | id, name, kind (`MONTH`/`YEAR`), year, month, reopened_on, reopened_by_user_id, reason, previous_signature, previous_closed_on, previous_closed_by_user_id, signature_was_valid |
| `audit_log` | id, name (Aktion), entity, entity_id, user_id, old_value, new_value; enthält nie Passwörter oder Hashes |

Das erstmalige Passwort wird nur als Hash abgelegt. Es kann zurückgesetzt werden und erzwingt bei der ersten Anmeldung einen Wechsel.

### 4.3 Buchungsdaten

| Tabelle | Wesentliche Felder |
| --- | --- |
| `bookings` | id, name, origin_date (Entstehungsdatum), booking_date, booking_type (`COST_CENTER_TO_ACCOUNT`, `ACCOUNT_TO_ACCOUNT`, `BUDGET_TRANSFER`), entry_side (`DEBIT`/`CREDIT`), amount_cents (**mit Vorzeichen, ≠ 0**), merchant, booking_text, reversal_of_id, fiscal_year, fiscal_month |
| `booking_legs` | id, booking_id, position (1 = führende Stelle, 2 = zweite Stelle), side (`DEBIT`/`CREDIT`), cost_center_id, account_id (genau eines von beiden) |

Regeln:

1. `amount_cents` ≠ 0, darf negativ sein.
2. Jede Buchung hat genau zwei Stellen (Zeilen in `booking_legs`). Bei `COST_CENTER_TO_ACCOUNT` stehen beide auf `entry_side`. Bei `ACCOUNT_TO_ACCOUNT` und `BUDGET_TRANSFER` steht die führende Stelle auf `entry_side` und die zweite auf der gegenüberliegenden Seite. Bei `BUDGET_TRANSFER` tragen beide Stellen eine Kostenstelle und kein Konto.
3. Die Vorzeichen der Beträge werden nie normalisiert.
4. Löschen ist nur in einem offenen Monat zulässig und wird protokolliert; danach nur durch Minusbuchung.

### 4.4 Plandaten

| Tabelle | Wesentliche Felder |
| --- | --- |
| `cost_center_plans` | id, name, cost_center_id, year, base_budget_cents (Basisansatz, ≥ 0, nach Aktivierung fix), budget_transfer_cents (Projektion aus `BUDGET_TRANSFER`), reserve_carry_in_cents, reserve_carry_out_cents |
| `monthly_plans` | id, name, cost_center_plan_id, month, plan_cents, reserve_plan_cents, plan_mode (`MONTHLY`, `QUARTERLY`, `IRREGULAR`, `RESERVE`) |
| `monthly_actuals` | id, name, cost_center_id, year, month, debit_cents, credit_cents, reserve_actual_cents |

`debit_cents` und `credit_cents` sind vorzeichenbehaftet und werden getrennt geführt. Die Ist-Bewegung ist `debit_cents − credit_cents`. `monthly_actuals` enthält ausschließlich Ist-Buchungen, nie Ansatzumbuchungen. Der wirksame Jahresansatz ist `base_budget_cents + budget_transfer_cents`; beides ist aus den Buchungen rekonstruierbar. Planung wird intern immer als Monatswerte gespeichert; Quartals- und unregelmäßige Planung sind Eingabehilfen.

## 5. Kernabläufe

### 5.1 Anmeldung

1. Anwender meldet sich an der Login-Oberfläche an; es gibt nur diese eine Zugangsstufe.
2. Der Hash wird geprüft; bei Fehler erscheint eine neutrale Meldung.
3. Bei `must_change_password` ist nur der Passwortwechsel möglich.
4. Danach wird das Menü angezeigt.

### 5.2 Buchung erfassen

1. Kostenstelle gewählt: Haushaltsrestbetrag, Monatsplan und bisherige Rückstellung werden angezeigt.
2. Konto gewählt: aktueller Kontostand wird angezeigt.
3. Betrag wird in Soll **oder** Haben erfasst, Vorzeichen frei.
4. Prüfung: Buchungszeitraum offen, Betrag ≠ 0, Buchungsart passend, Ansatzsperre (siehe 2.7). Bei Sperre wird die Ansatzumbuchung angeboten.
5. In **einer Transaktion**: Buchung, Buchungsseiten, Plan-Ist-Fortschreibung bzw. Ansatzfortschreibung, Audit-Eintrag.
6. Erfolg wird erst nach Commit gemeldet.

### 5.3 Monatsabschluss

1. Der Monat muss der älteste offene Monat sein.
2. Die Daten werden geprüft, das Abschlussdatum wird gesetzt und eine Signatur (SHA-256 über kanonisch serialisierte Buchungen des Monats, inklusive Vorzeichen und Seite) abgelegt.
3. Der Monat ist danach unveränderbar. `last_closed_month` und `current_month` werden fortgeschrieben.

Die Signatur macht nachträgliche Änderungen erkennbar; sie ersetzt keine rechtlich revisionssichere Archivierung.

### 5.4 Wiedereröffnen eines Abschlusses

Ein Abschluss kann ausnahmsweise wiedereröffnet werden. Das ist ein eigener, dokumentierter Sonderprozess:

1. **Umgekehrte Reihenfolge:** Es kann nur der zuletzt liegende Abschluss wiedereröffnet werden. Die Reihenfolge ist chronologisch, wobei der Jahresabschluss hinter dem Dezember seines Jahres und vor dem Januar des Folgejahres steht. Ein Jahresabschluss ist also vor den Monaten seines Jahres zu öffnen, und Monate späterer Jahre vor ihm. Bei einem Verstoß nennt die Meldung, was zuerst wiedereröffnet werden muss.
2. **Begründung:** Eine Begründung (mindestens 10 Zeichen) ist Pflicht.
3. **Dokumentation:** Der Vorgang wird dauerhaft in `closure_reopenings` festgehalten, mit Art und Zeitraum, Anwender, Datum, Begründung, der verworfenen Signatur, ursprünglichem Abschlussdatum und -anwender sowie dem Ergebnis der Signaturprüfung zum Zeitpunkt des Wiedereröffnens („Signatur zuvor gültig“). Zusätzlich entsteht ein Audit-Eintrag. Die Einträge werden nie gelöscht und bleiben auch nach erneutem Abschluss bestehen.
4. **Wirkung:** Der Abschluss entfällt. Bei einem Monat springt der Buchungsmonat auf diesen Monat zurück, und `last_closed_*` zeigt auf den vorherigen Abschluss. Der Zeitraum ist wieder änderbar. Beim erneuten Abschluss entsteht eine neue Signatur.
5. Eine ungültige Signatur verhindert das Wiedereröffnen nicht, wird aber als solche vermerkt. So ist erkennbar, wenn Daten nach dem Abschluss verändert wurden.

## 6. Fehlerbehandlung und Nachvollziehbarkeit

- Fachliche Fehler: konkrete deutsche Meldung mit Hinweis auf die Ursache.
- Technische Fehler: lokale Protokollierung mit Kontext, Anwender sieht eine allgemeine Meldung.
- Änderungen an Stammdaten, Steuerung, Plan und Buchungen werden mit Anwender, Zeit, Aktion und alt/neu im Audit-Protokoll festgehalten.

## 7. Offene fachliche Entscheidungen

Bereits entschieden und bestätigt: Planwerte in Soll-Richtung mit Jahresansatz ≥ 0 (2.3), Monatsplan nur als Anzeige ohne Sperre (2.7), Trennung „Ansatzhöhe per Buchung, Verteilung in der Planung“ (2.8) und die Haushaltsreserve (2.9).

Noch offen:

1. **Rückstellungen:** Bildung und Auflösung im Detail, insbesondere ihr Verhältnis zur Ansatzsperre.
2. **Anfangssalden und Planübertrag:** manuell, per Abschluss oder beides.
3. **Art „ohne Plan“:** führt nur Soll- und Haben-Summe; weitere Arten (z. B. „??“ im Ausgangsdokument) sind noch zu benennen.
4. **Mehrbenutzerbetrieb:** SQLite eignet sich für lokale Einzelplatznutzung. Bei paralleler Nutzung mehrerer Anwender ist ein Datenbankwechsel einzuplanen.
5. **Kostenstellenrechnung und Auswertungen:** Inhalte und Kennzahlen folgen.
