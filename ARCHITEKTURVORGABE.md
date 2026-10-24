# Meine Kasse – Architekturvorgabe

Version 3 – Grundlage: Dokument „PDVM Meine Kasse“, Klarstellung zu Negativbeträgen und [Testergebnisse 1](./ANALYSE_TESTERGEBNISSE_1.md). Die dort getroffenen Entscheidungen E1–E7 sind eingearbeitet (siehe Abschnitt 7).

## 1. Ziel und Geltungsbereich

Meine Kasse ist eine deutschsprachige Desktop-Anwendung (Python, integrierte SQLite) für eine einfache Buchhaltung auf Kostenstellen und Konten (Bank oder Anlagen).

Umfang des ersten Ausbaustands:

- Anmeldung mit lokal verwalteten Anwendern (ohne Berechtigungskonzept), danach Hauptmenü
- Stammdaten und Steuerung: Kostenstellen, Konten, Anwender, Buchungssteuerung
- Buchungen mit Soll/Haben, positiven **und negativen** Beträgen
- Planung je Kostenstelle (Jahressumme, Monatswerte, Rückstellungen) sowie Einnahmenplanung auf Einnahmen-Kostenstellen (2.15)
- Soll-/Ist-Abgleich direkt bei jeder Buchung mit **Sperre bei Überschreitung des Ansatzes**
- Ansatzumbuchungen zwischen Kostenstellen
- Monats- und Jahresabschluss mit Signaturen
- Rückstellungen je Kostenstelle mit maschineller Verteilung (2.12)
- Internes Cash-Management (2.13)
- Komfortfunktionen für Tabellen und Auswahlen, PDF-Ausgabe mit Dokumentenarchiv, Auswertungsdialog mit speicherbaren Auswertungen (2.14)

Nicht Bestandteil: Fremdwährungen (nur €), Berechtigungsstufen, Bankanbindung, mehrstufige Sortierung in Tabellen (Ausnahme: Gruppierung in Auswertungen).

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
| Konto → Konto (nur Altbestand), Ansatz Kostenstelle → Ansatz Kostenstelle | **Gegenläufig:** Die erste (führende) Stelle wird auf der Erfassungsseite gebucht, die zweite auf der gegenüberliegenden. Das ist fachlich zwingend, weil die Quelle abgibt und das Ziel erhält. |
| Umbuchung zwischen Konten (2.4a) | Zwei Buchungssätze Kostenstelle → Konto: führendes Konto mit Kostenstelle im **Soll**, Umbuchungskonto mit Kostenstelle im **Haben**. |

Es gibt keine Sachkonten und keine doppelte Buchführung im klassischen Sinn („Kostenstelle an Bank“ entfällt). Sachkonten wären nur für Bilanz und GuV nötig. Eine Kategorie kann später als Merkmal ergänzt werden.

Wirkung eines Betrags `b` (mit Vorzeichen) auf jede Stelle, die auf der betreffenden Seite gebucht wird:

| Erfassungsseite | Soll-Summe | Haben-Summe | Nettobewegung (Soll − Haben) |
| ---             | ---        | ---         | ---                          | 
| Soll, `b`       | + b        | –           | + b                          |
| Haben, `b`      | –          | + b         | − b                          |

Beispiele:

- Ausgabe 50 € für Lebensmittel, bezahlt vom Girokonto: Soll 50 € bei der Kostenstelle **und** Soll 50 € beim Girokonto. Kontostand und Haushaltsrest sinken um 50 €.
- Erstattung 20 €: Haben 20 € bei beiden Stellen. Wird sie als Soll −20 € erfasst, bleibt das ebenfalls so gespeichert (kein Seitentausch). Die Wirkung auf Saldo und Haushaltsrest ist gleich, die Erfassung bleibt unterscheidbar.

**Kontrollsumme:** Die Summe der Kontenbewegungen aus Ist-Buchungen (Haben − Soll) muss der Summe der Ist-Bewegungen aller Kostenstellen (Haben − Soll) entsprechen. Umbuchungen zwischen Konten haben je Konto eine Kostenstelle und ergeben in Summe 0 auf den Konten. Diese Prüfung ersetzt die Soll = Haben-Kontrolle der Doppik.

### 2.3 Auswirkungen auf Planung und Abgleich

| Bereich | Festlegung | Status |
| --- | --- | --- |
| Soll/Haben getrennt führen | Die Ist-Werte führen Soll-Summe und Haben-Summe **getrennt und mit Vorzeichen**. Beide können negativ sein. Die echte Bewegung ist `Soll − Haben`. | festgelegt |
| Haushaltsrestbetrag | `Jahresansatz − Ist-Bewegung (Soll − Haben)`. Negative Buchungen erhöhen den Restbetrag, Buchungen mit Haben-Seite ebenfalls. | festgelegt |
| Monatsabgleich | Der Plan-Ansatz des Monats wird mit der Ist-Bewegung des Monats verglichen, jeweils vorzeichenrichtig. | festgelegt |
| Rückstellung ist | Wird je Kostenstelle und Planmonat aus der Ist-Bewegung und der Rückstellungsplanung berechnet (2.12). Es gibt keine Buchungen auf Rückstellungen. | festgelegt |
| Storno/Korrektur | Eine Buchung wird durch eine **Minusbuchung auf derselben Seite** (gleiche Stellen, Betrag mit umgekehrtem Vorzeichen) korrigiert, verknüpft über `reversal_of_booking_id`. Das entspricht dem klassischen Rotstorno und verändert die Seite nicht. | festgelegt |
| Vorzeichen von Planwerten | Planwerte (Jahresansatz, Monatsplan, Rückstellungsplan, Übertrag) werden in Soll-Richtung geführt, also mit **derselben Konvention** wie Ist-Werte. Der Basisansatz und die Monatsplanwerte sind immer ≥ 0. Der wirksame Jahresansatz ist normalerweise ≥ 0 und wird nur negativ, wenn Haushaltsrest ohne Ansatz weitergegeben wurde (2.7, Regel 2a). Plan und Ist sind damit ohne Umrechnung vergleichbar. | festgelegt |
| Überschreitung | Eine Überschreitung des Jahresansatzes **sperrt** die Buchung (siehe 2.7). | festgelegt |
| Einnahmen/Ausgaben | Kostenstellen und Konten werden **nicht** als Einnahme- oder Ausgabeobjekt gekennzeichnet. Einnahmen und Erstattungen sind Haben- bzw. Minusbuchungen und entlasten die Kostenstelle über die Vorzeichenlogik. **Ausnahme:** Planbare und nicht planbare Einnahmen (Rente, Entgelte, Zinsen) liegen auf Kostenstellen der Art `INCOME` (2.15). | festgelegt |

### 2.4 Buchungsarten

| Art (`booking_type`) | Führende Stelle | Zweite Stelle | Seite der zweiten Stelle | Wirkung |
| --- | --- | --- | --- | --- |
| Kostenstelle → Konto (`COST_CENTER_TO_ACCOUNT`) | Kostenstelle | Konto | gleich | Ist der Kostenstelle und Saldo des Kontos; unterliegt der Ansatzsperre |
| Konto → Konto (`ACCOUNT_TO_ACCOUNT`) | Konto | Konto | gegenläufig | **nicht mehr buchbar** (nur Altbestand, siehe 2.4a) |
| Ansatz Kostenstelle → Ansatz Kostenstelle (`BUDGET_TRANSFER`) | Kostenstelle | Kostenstelle | gegenläufig | nur Jahresansatz beider Kostenstellen; kein Ist, keine Konten |

Zulässige Kombinationen werden zentral je Buchungsart definiert und validiert. Die Kontoart (Giro, Spar, Anlage, Rückstellung) wird nicht mit der Planposition „Rückstellung“ vermischt.

Die frühere Art „Kostenstelle an Kostenstelle“ als Ist-Umbuchung entfällt. Falsch zugeordnete Ist-Buchungen werden durch Minusbuchung und neue Buchung korrigiert (siehe 2.3).

### 2.4a Umbuchung zwischen Konten

Keine Bewegung auf einem Konto ohne Gegenstelle: Jede Kontobewegung hat eine Kostenstelle als Gegenstelle. Eine Umbuchung zwischen zwei Konten wird deshalb mit **je einer Kostenstelle pro Konto** erfasst und in **zwei Buchungssätze** vom Typ `COST_CENTER_TO_ACCOUNT` geteilt:

| Satz | Stellen | Seite |
| --- | --- | --- |
| 1 | Kostenstelle (Soll) und führendes Konto | Soll (Ausgabe) |
| 2 | Kostenstelle (Haben) und Umbuchungskonto | Haben |

- Beide Sätze haben denselben Betrag (mit Vorzeichen, ≠ 0), dasselbe Buchungs- und Entstehungsdatum, Händler und Buchungstext. Sie sind über die gemeinsame GUID `bookings.transfer_id` verbunden.
- Führendes Konto und Umbuchungskonto müssen verschieden sein; die beiden Kostenstellen dürfen gleich sein (die Wirkung auf die Kostenstelle ist dann 0).
- Der Soll-Satz unterliegt wie jede Ist-Buchung der Ansatzsperre; die Sperre wird auf die Nettowirkung beider Sätze geprüft. Beide Sätze entstehen in **einer** Transaktion.
- Ändern, Löschen und Stornieren wirken immer auf beide Sätze gemeinsam. Die Stornos bilden wieder eine Umbuchung (neue `transfer_id`, je Satz `reversal_of_id`) und können nur gemeinsam gelöscht werden. Ein einzelner Satz einer Umbuchung ist in der Buchungsmaske nicht änderbar.
- Die Summe der Kontenbewegungen entspricht weiterhin der Summe der Ist-Bewegungen aller Kostenstellen (2.2).
- Altbestand: Bereits vorhandene Buchungen vom Typ `ACCOUNT_TO_ACCOUNT` bleiben unverändert erhalten und werden in Salden und Abschlüssen weiter berücksichtigt. Sie können gelöscht oder storniert, aber nicht mehr geändert werden. Neue Buchungen dieser Art werden abgelehnt.

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
2. Eine Ansatzumbuchung wird abgelehnt, wenn bei der abgebenden Kostenstelle danach der Jahresansatz kleiner als die Ist-Bewegung (Haushaltsrest unter 0) oder kleiner als der verteilte Ansatz wäre.
2a. **Haushaltsrest ohne Ansatz:** Ist die Ist-Bewegung negativ (z. B. Zuführung von Außenmitteln auf eine Kostenstelle ohne Ansatz) und ist nichts auf Monate verteilt, darf der Haushaltsrest per Ansatzumbuchung weitergegeben werden, auch wenn der Ansatz dafür nicht reicht. Der wirksame Jahresansatz der abgebenden Stelle wird dann negativ (Ansatz − Ist-Bewegung bleibt ≥ 0). Das erfordert eine **Sicherheitsabfrage**, die Höhe und den entstehenden negativen Ansatz nennt; ohne Bestätigung wird nicht gebucht. Das gilt auch für Löschen und Stornieren, wenn dadurch ein negativer Ansatz entsteht. Ein negativer Ansatz lässt keine Verteilung auf Monate und keine Zuführung zu; der Basisansatz bleibt ≥ 0. Das Verringern oder Stornieren der Zuführungsbuchung unter den weitergegebenen Betrag verhindert Regel 1 (Haushaltsrest nie unter 0); vorher ist die Umbuchung per Storno zurückzunehmen.
3. Ansatzumbuchungen sind nur bei aktivierter Planung, zwischen zwei verschiedenen Kostenstellen der Art `STANDARD` und in einem offenen Zeitraum möglich. Zusätzlich darf eine Kostenstelle der Art `INCOME` als **abgebende** Stelle an eine `STANDARD`-Kostenstelle umbuchen (2.15); sie erhält nie Ansatz.
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
| Verteilung auf Monate und unregelmäßige Beträge innerhalb des Jahresansatzes, Zuführungen zur Rückstellung | Planung (Planungsdialog), ohne Buchung | Gesamtsumme ändert sich nicht, Vorgang ist reine Planungsarbeit |

Regeln dazu:

- Die Summe der Monatsplanwerte darf den wirksamen Jahresansatz nicht überschreiten. Die Differenz ist der unverteilte Ansatz.
- Die empfangende Kostenstelle verteilt den erhaltenen Ansatz anschließend selbst in der Planung. Die abgebende Kostenstelle kann nur unverteilten Ansatz abgeben oder muss ihre Monatsplanung zuvor verringern.
- Planänderungen sind nur in offenen Monaten möglich und werden im Audit-Protokoll festgehalten.
- Die Signatur eines Monatsabschlusses umfasst auch die Ansatzumbuchungen und Monatsplanwerte des Monats.
- Die Planungsart (`plan_mode`) entfällt als Bedienelement. Es gibt keine Quartalsverteilung mehr. „Gleichmäßig verteilen“ bleibt als Eingabehilfe, der Standardknopf des Planungsdialogs ist „Speichern“. Die Spalte `plan_mode` bleibt im Schema und in der Signatur unverändert erhalten (Rückwärtskompatibilität bestehender Abschlüsse); vorhandene Werte werden beim Speichern unverändert durchgereicht, neue Monate sind `MONTHLY`.
- Hat eine Kostenstelle keinen Ansatz, kann darauf nur gebucht werden, nachdem ihr per Ansatzumbuchung Ansatz bereitgestellt wurde (ergibt sich aus der Ansatzsperre, 2.7). Hat sie dagegen keinen Ansatz, aber Haushaltsrest (z. B. aus Außenmitteln), kann dieser per Ansatzumbuchung nach Sicherheitsabfrage weitergegeben werden (2.7, Regel 2a); eine eigene Buchungsart gibt es dafür nicht.

Gegenüber „alles über Buchungen“ erzeugt dieser Weg keine Buchungen ohne fachlichen Wert für reine Umverteilungen. Gegenüber „alles in der Planung“ bleibt jede Änderung der Ansatzhöhe nachvollziehbar.

### 2.9 Haushaltsreserve

Zusätzliche Mittel (z. B. höheres Einkommen) werden über eine normale Kostenstelle „Haushaltsreserve“ der Art `STANDARD` abgebildet. Sie erhält ihren Ansatz wie jede andere Kostenstelle, und daraus wird per Ansatzumbuchung auf andere Kostenstellen verteilt. Es gibt keine Ansatzänderung ohne Gegenstelle und keine Sonderart für diese Kostenstelle.

### 2.10 Anfangssalden der Konten (Jahresvortrag)

Der **Kontostand** ist der Anfangssaldo (Vortrag) plus die Bewegung (Haben − Soll) aller Buchungen des Kontos. Anfangssalden sind vorzeichenbehaftet, ein überzogenes Konto ist also möglich.

| Regel | Festlegung |
| --- | --- |
| Erfassung | Je Konto gibt es **höchstens einen** manuell erfassten Vortrag zum 01.01. eines Jahres (`account_opening_balances`). |
| Vorjahr | Hat das Konto ein Vorjahr (Buchungen oder ein Vortrag in einem früheren Jahr), ist der Vortrag **nicht editierbar** und wird aus Vortrag plus Buchungen der Vorjahre abgeleitet. |
| Editierbar bis | Ein manuell erfasster Vortrag ist editierbar, **bis der Januar des Jahres abgeschlossen ist** (oder das Jahr). Danach ist er gesperrt. Nach dem Wiedereröffnen des Januars ist er wieder editierbar. |
| Verschieben | Ein Vortrag kann auf ein **früheres** Jahr verschoben werden, solange sein bisheriger Januar offen ist. Ein späteres Jahr ist nach einem Vortrag immer abgeleitet. |
| Entfernen | Ein leeres Feld entfernt den Vortrag, der Kontostand beginnt dann bei 0,00 €. |
| Kein Buchen davor | Auf ein Konto mit Vortrag kann nicht mit einem Buchungsdatum vor dem 01.01. des Vortragsjahres gebucht werden. |
| Signatur | Im Januar-Abschluss gehen die Anfangssalden des Jahres in die Signatur ein. Ohne Anfangssalden bleibt die Signatur unverändert. |
| Kontrollsumme | Die Kontrollsumme Konten gegen Kostenstellen (2.2) betrifft nur Bewegungen, Anfangssalden beeinflussen sie nicht. |

### 2.11 Zwei Zeitachsen: Buchungsperiode und Planperiode

Jede Buchung hat zwei Daten mit getrennter Aufgabe:

| Datum | Bestimmt | Gilt für |
| --- | --- | --- |
| Buchungsdatum (`booking_date`) → **Buchungsperiode** (`fiscal_year`, `fiscal_month`) | Abschluss, Signatur, Buchbarkeit (2.5), Kontenbewegung | Konten, Abschlüsse |
| Entstehungsdatum (`origin_date`) → **Planperiode** | Planmonat und Planjahr der Plan-Ist-Fortschreibung, Ansatzsperre, Rückstellung | Kostenstellen (`monthly_actuals`) |

Regeln:

1. Die Ist-Werte einer Kostenstelle werden im Monat des **Entstehungsdatums** fortgeschrieben, nicht im Monat des Buchungsdatums.
2. Die Buchbarkeit nach 2.5 gilt für das Buchungsdatum. Der Planmonat darf bereits abgeschlossen sein, solange das **Planjahr** nicht abgeschlossen ist. Die Monatssignatur bleibt unberührt, weil sie über die Buchungsperiode gebildet wird.
3. Liegt das Entstehungsdatum im **Vorjahr** (allgemein: in einem anderen Planjahr als dem laufenden), wird dort gebucht, wenn für die Kostenstelle in diesem Jahr ein Plan existiert und das Jahr nicht abgeschlossen ist. Andernfalls wird **nicht gebucht**; der Anwender erhält einen Hinweis mit Kostenstelle, Planjahr und Grund (kein Plan vorhanden / Jahr abgeschlossen).
4. Ein Storno übernimmt das Entstehungsdatum der Ursprungsbuchung, damit er im selben Planmonat ausgleicht. Ist dieses Planjahr abgeschlossen, wird das Datum des Storno als Entstehungsdatum verwendet.
5. Bei einer Änderung des Entstehungsdatums werden alter und neuer Planmonat in einer Transaktion fortgeschrieben.
6. Der Neuaufbau der Plan-Ist-Werte (`rebuild_projections`) und die Abschlussprüfung verwenden die Planperiode.
7. „Anderes Planjahr“ bedeutet: ungleich dem aktuellen Buchungsjahr der Buchungssteuerung. Die Planprüfung gilt nur für Ist-Buchungen (Kostenstelle → Konto) auf Kostenstellen der Art `STANDARD` bei aktiver Planung. Ein abgeschlossenes Planjahr wird dagegen immer abgelehnt. Als Plan gilt ein vorhandener Jahresplan der Kostenstelle (auch ein durch Ansatzumbuchung entstandener).
8. Eine Buchung, deren Planjahr nachträglich abgeschlossen wurde, kann nicht mehr geändert oder gelöscht, sondern nur noch storniert werden. Der Storno wirkt dann im Jahr seines eigenen Datums.
9. Ansatzumbuchungen gehören zum Buchungsjahr; das Entstehungsdatum spielt für sie keine Rolle.
10. In der Buchungsmaske zeigen die Kostenstellenangaben den Stand der Planperiode des Entstehungsdatums; ist sie nicht bebuchbar, erscheint der Grund dort und als Hinweisdialog beim Speichern.

### 2.12 Rückstellungen

Eine Rückstellung ist je Kostenstelle ein **virtuelles Rückstellungskonto**. Es ist kein Datensatz in `accounts` und fließt nicht in Kontosalden oder Kontrollsumme ein. Es wird aus Plan und Ist berechnet und kann nicht direkt bebucht werden.

Begriffe (aus Sicht der Rückstellung; Soll = Bildung, Haben = Entlastung, Bestand = Soll − Haben):

| Begriff | Bedeutung |
| --- | --- |
| Zuführung (Rückstellung Soll, Plan) | je Monat gebildete Rückstellung (`reserve_plan_cents`) |
| Planentlastung (Rückstellung Haben, Plan) | die direkt geplanten Zahlungen (`plan_cents`) im Zahlungsmonat entlasten die Rückstellung |
| Entlastung ist (Rückstellung Haben, Ist) | tatsächlich durch Ist-Buchungen entlasteter Betrag (`reserve_actual_cents`) |
| Vortrag | Bestand zum Jahresende, wird als Anfangsbestand in das Folgejahr übernommen |

Regeln:

1. **Direkte Planung:** Ein Ansatz wird im Monat der voraussichtlichen Zahlung geplant. Ist in allen zwölf Monaten ein Planwert vorhanden, entstehen keine Rückstellungen.
2. **Maschinelle Verteilung:** Ist nicht jeder Monat belegt, wird der **gesamte** Jahresansatz gleichmäßig auf die freien Monate als Zuführung verteilt (Rundungsrest an die ersten Monate). Danach wird je Zahlungsmonat geprüft, ob Vortrag plus Zuführungen bis einschließlich dieses Monats die geplanten Zahlungen (kumuliert) decken. Fehlt Deckung, werden die Zuführungen **vor der Zahlung erhöht**, und zwar in den freien Monaten seit der letzten Deckungslücke; die Monate nach der Zahlung erhalten entsprechend weniger. Die Summe der Zuführungen bleibt dadurch gleich und übersteigt den Jahresansatz nie, kein Monat wird negativ. Reicht der Ansatz oder die Zahl freier Monate nicht aus, erscheint ein Hinweis im Planungsdialog (Monat und Fehlbetrag).
3. **Manuelle Anpassung:** Die Zuführung ist je Monat änderbar. Ein von Hand gesetzter Monat ist gekennzeichnet (`reserve_is_manual`) und wird von der maschinellen Verteilung nicht überschrieben; ein leeres Feld macht ihn wieder maschinell. Die Schaltfläche „Rückstellung maschinell“ verwirft die manuellen Werte der offenen Monate. Abgeschlossene Monate werden nie verändert. Die Summe der Zuführungen darf den Jahresansatz nicht übersteigen (sonst wird nicht gespeichert).
4. **Keine negativen Rückstellungen:** Der Bestand ist nie kleiner als 0. Es wird nicht gegen künftige Zuführungen entlastet.
5. **Entlastung bei Buchung:** Eine Ist-Bewegung der Kostenstelle entlastet die Rückstellung nur bis zum verfügbaren Bestand (Vortrag + Zuführungen bis einschließlich Planmonat − bisherige Entlastungen). Ist der Bestand zu gering, erscheint nach dem Speichern ein Hinweis mit dem Fehlbetrag; die Buchung wird dennoch ausgeführt. Ohne Rückstellung im Planjahr (z. B. bei Planung in allen Monaten) gibt es keinen Hinweis. Die Buchungsmaske zeigt den Rückstellungsbestand bis zum Planmonat.
6. **Berechnung nach Monatssummen:** Die Entlastung wird je Planmonat aus der Monatssumme der Ist-Bewegung berechnet, nicht aus der Reihenfolge einzelner Buchungen. Damit ist sie jederzeit aus den Buchungen neu aufbaubar (Entwicklungsregel 3.11). Eine negative Monatsbewegung (Erstattung) gibt Entlastung höchstens bis zur bisherigen Entlastung zurück.
7. **Ansatzsperre:** Unverändert (2.7). Die Rückstellung unterteilt den Jahresansatz und erweitert ihn nicht. Zuführung und Planentlastung sind Planung und berühren Ist, Haushaltsrest und Konten nicht.
8. **Jahreswechsel:** Der nicht ausgeglichene Bestand (Endbestand Dezember) ist der Vortrag ins Folgejahr. Hat die Kostenstelle im Vorjahr einen Plan, wird der Vortrag von dort übernommen und ist nicht editierbar. Ohne Vorjahresplan wird er von Hand erfasst, solange der Januar des Jahres nicht abgeschlossen ist. Der Vortrag ist eine Projektion und aus den signierten Buchungen und Plänen jederzeit ableitbar; eine eigene Signatur gibt es nicht. Die Abschlussprüfung vergleicht gespeicherte Entlastung und Vorträge mit der Neuberechnung und bricht bei Abweichung ab (Projektionen neu aufbauen).
9. **Reale Deckung:** Das Geld für Rückstellungen wird manuell per Umbuchung (2.4a) auf das Betriebsmittelkonto bewegt (2.13). Das System bucht dies nicht automatisch.
10. **Auslöser der Berechnung:** Zuführungen werden beim Speichern der Planung berechnet (im Dialog als Live-Vorschau). Entlastung und Vorträge werden bei jeder Buchung, Änderung, Löschung und Stornierung in derselben Transaktion fortgeschrieben, über alle folgenden Planjahre hinweg, sowie beim Neuaufbau der Projektionen und beim Programmstart.
11. **Bestand aus früheren Versionen:** Bisher von Hand erfasste Zuführungen (> 0) gelten nach der Migration als manuell und bleiben unverändert.

### 2.13 Cash-Management

Der Dialog zeigt je Monat bis einschließlich des aktuellen Buchungsmonats folgende Werte:

| Block | Inhalt |
| --- | --- |
| Kontosalden | berechneter Kontostand je Konto (Anfangssaldo + Bewegung) und ergänzend der Rückstellungsbestand |
| Kontenabgleich | manuell eingetragener erwarteter Kontostand (z. B. laut Kontoauszug), berechneter Kontostand und Differenz; die Differenz erscheint sofort beim Öffnen |
| Zahlungskonto | Saldo des zentralen Zahlungskontos abzüglich noch offener Planausgaben = verfügbarer Rest (Cash), in zwei Spalten: offen im aktuellen Monat und offen bis Jahresende |
| Betriebsmittel | Saldo des Betriebsmittelkontos, Bewegung im laufenden Jahr, Planbetrag, Rückstellungen Soll/Haben bis zum laufenden Monat und Differenz |

Regeln:

1. Ein Konto trägt höchstens eine Rolle (`cash_role`: `NONE`, `CENTRAL_PAYMENT`, `OPERATING_FUNDS`). Je Rolle gibt es höchstens ein Konto.
2. Der erwartete Kontostand wird je Konto und Monat gespeichert. Fehlt ein Eintrag, gilt der letzte frühere Eintrag, bis er geändert wird. Änderungen werden im Audit-Protokoll festgehalten.
3. Die Differenz Betriebsmittelsaldo ↔ Rückstellungsbestand ist eine Kontrollgröße, keine Sperre.
4. Der Dialog ist lesend; nur der erwartete Kontostand ist editierbar.

### 2.15 Einnahmen-Kostenstellen (`INCOME`)

Einnahmen wie Rente, PV-Entgelt, Entgelt für Orgelspiel oder Zinsen haben keinen Jahresansatz. Sie werden **erwartet** (Plan) und **gebucht** (Ist) und erst durch eine Ansatzumbuchung zum Ansatz einer Kostenstelle mit Plan. Dafür gibt es die Kostenstellenart `INCOME` mit dem Modus `income_mode`.

| Aspekt | Festlegung |
| --- | --- |
| Art und Modus | `kind = INCOME`, dazu `income_mode` (`PLAN` oder `ACTUAL`, Standard `PLAN`). Art und Modus sind nach dem Anlegen fest. Bei allen anderen Arten ist `income_mode` leer. |
| Plan | `monthly_plans.plan_cents` ist die **erwartete Einnahme** des Monats (≥ 0). Es gibt keine Rückstellung (`reserve_plan_cents` = 0), keinen Basisansatz (`base_budget_cents` = 0) und keine Verteilungsgrenze. Die Planung läuft im eigenen Dialog „Einnahmenplanung“ (Gleichmäßig verteilen als Eingabehilfe, abgeschlossene Monate gesperrt). |
| Ist | Buchung Kostenstelle → Konto, Haben auf der Einnahmenstelle. Ist-Einnahme = Haben − Soll. Die Planperiode folgt dem Entstehungsdatum (2.11). Es gibt weder Ansatzsperre noch Planjahrprüfung; eine Einnahme ist auch ohne Plan buchbar. |
| Abgleich | Je Monat Plan, Ist und Abweichung (Ist − Plan) nur als Anzeige. Noch erwartet = Summe je Monat von (Plan − Ist-Einnahme), nie negativ. |
| Weitergabe | Die Ansatzumbuchung der Einnahmenstelle an eine `STANDARD`-Kostenstelle steht als negativer `budget_transfer_cents` im Jahresplan der Einnahmenstelle (weitergegeben = −`budget_transfer_cents`). |
| Verfügbar `PLAN` | Verlässliche Einnahme (z. B. Rente): umbuchbar ist der Jahresplan, mindestens aber die bereits gebuchte Einnahme. |
| Verfügbar `ACTUAL` | Unsichere Einnahme (z. B. Zinsen, Orgelspiel): umbuchbar ist nur die bereits gebuchte Einnahme (Vorsichtsprinzip). |
| Noch umbuchbar | verfügbar − bereits weitergegeben. Eine Umbuchung darüber wird mit Hinweis auf den möglichen Betrag abgelehnt. |
| Deckung | Der weitergegebene Betrag muss gedeckt bleiben: Ein Plan, der unter ihn sinkt, sowie das Verringern, Löschen oder Stornieren von Einnahmebuchungen unter ihn wird abgelehnt. Vorher ist die Umbuchung per Storno zurückzunehmen. |
| Nicht planbar | Eine nicht erwartete Einnahme (Plan 0) wird nach Eingang gebucht und, bei Modus `ACTUAL`, per Ansatzumbuchung auf die Haushaltsreserve (2.9) oder eine andere Kostenstelle verteilt. |
| Abschluss | Plan und Ist der Einnahmenstelle gehen wie bei jeder Kostenstelle in die Monatssignatur ein (2.5). |

Mit `INCOME` als Empfänger sind Ansatzumbuchungen nicht möglich, ebenso nicht zwischen zwei Einnahmenstellen und nicht an `WITHOUT_PLAN`.

### 2.14 Bedienung, Tabellen, Ausgabe und Auswertungen

**Eingaben**

1. Buchungsdatum: Standardvorgabe ist das zuletzt verwendete Buchungsdatum; liegt es nicht im Buchungsmonat, der 1. des Buchungsmonats. Das Eingabefeld akzeptiert einen **Tag** (ergibt Datum im Buchungsmonat) oder ein vollständiges Datum.
2. Entstehungsdatum: Tag oder vollständiges Datum, Standard im Buchungsmonat. Wird der Tag übergangen, ist das Datum frei änderbar.
3. Alle Auswahllisten (Kostenstelle, Konto, Anwender) sind per Texteingabe filterbar; Filter wirkt auf Teilstrings in Name und Nummer, nicht nur auf den Anfang.
4. Standardschaltflächen und Rückfragen sind deutsch (Ja/Nein/Abbrechen/OK).

**Tabellen**

1. Jede Spalte hat ein Suchfeld, das die Anzeige einschränkt, und ist auf- und absteigend sortierbar (einstufig). Sortierung nach Rohwerten (Cent, Datum), nie nach Anzeigetext.
2. Sortierung wird je Anwender und Tabelle gespeichert (`user_settings`, Spalte über ihre Überschrift identifiziert). Spaltenfilter gelten nur für die geöffnete Ansicht; gespeicherte Filter gehören zu den Auswertungen. Die Buchungsliste bietet Filter nach Konto und Kostenstelle zusätzlich zum Monat.
3. Der Inhalt einer Tabelle kann „wie dargestellt (gefiltert, sortiert)“ als PDF ausgegeben werden. Die Tabellenkomponente liefert dafür die angezeigten Zeilen in Anzeigereihenfolge.
4. Reine Eingabetabellen (Monatsraster der Planung und des Abschlusses, Kontenanfangssalden) verwenden die Komponente nicht, weil Sortierung und Filter dort die Zeilenzuordnung der Eingabe stören würden.

**PDF und Dokumentenarchiv**

1. Die PDF-Datei wird unter `%LOCALAPPDATA%\MeineKasse\Dokumente` abgelegt. Dateiname: maschineller Teil (Zeitstempel, Tabellenname) plus manueller Zusatz (höchstens 40 Zeichen, unzulässige Dateizeichen werden entfernt).
2. Jede erzeugte Datei wird in `documents` registriert (Name, Art, Ersteller, Zeitpunkt, Größe, SHA-256). Das Dokumentenarchiv ist aus der Anwendung erreichbar, durchsuch- und sortierbar; Anzeige und Druck erfolgen im PDF-Programm des Systems.
3. Die PDF-Erzeugung läuft über einen Port der Anwendungsschicht, die Umsetzung liegt in der Infrastruktur (austauschbar).
4. Die Datensicherung enthält Datenbank **und** Dokumentenverzeichnis.

**Auswertungen**

0. **Grundsatz:** Es gibt **eine** allgemeine Auswertung über Datenquellen und einen erweiterbaren Spaltenkatalog statt vieler Einzelberichte. Fachfragen werden durch Spaltenwahl, Filter, Gruppierung und gespeicherte Auswertungen beantwortet. Eine **Spezialfunktion** (eigener Dialog mit eigener Logik) entsteht nur, wenn die Antwort Berechnungen erfordert, die keine Spalte einer Datenquelle sind (z. B. Cash-Management, Abschlussprüfung). Der Spaltenkatalog startet mit den in 2.14 genannten Spalten und wächst nach Bedarf; eine neue Spalte ist eine Katalogzeile, kein neuer Bericht.
1. Eine Auswertung arbeitet auf einer **Datenquelle** mit fester Zeilenbedeutung. Spalten gehören zu genau einer Datenquelle:

| Datenquelle | Zeile | Beispielspalten |
| --- | --- | --- |
| Buchungen | Buchung | Buchungs-/Entstehungsdatum, Kostenstelle, Konto, Gegenkonto, Buchungsart, Soll, Haben, Text, Händler, Status (offen/abgeschlossen, Storno), Anwender |
| Plan/Ist | Kostenstelle × Planmonat | Kostenstelle, Soll, Haben, Ist-Bewegung, Monatsplan, Abweichung, Ansatz, Restansatz, Zuführung, Entlastung, Rückstellungsbestand |
| Konten | Konto | Konto, Art, Anfangssaldo, Soll, Haben, Saldo, erwarteter Kontostand, Differenz |

2. Jede Spalte ist `ADDITIVE` (summierbar: Soll, Haben, Bewegung, Monatsplan, Zuführung, Entlastung) oder `NON_ADDITIVE` (Bestands- und Jahreswerte: Ansatz, Restansatz, Rückstellungsbestand, Saldo). Gesamt- und Gruppensummen summieren nur `ADDITIVE`-Spalten; bei `NON_ADDITIVE` wird je Gruppe der Wert der letzten Zeile bzw. nichts ausgewiesen.
3. Spalten sind frei ein- und ausblendbar. Eine Auswertung speichert Name, Datenquelle, Spaltenauswahl und -reihenfolge, Filter, Sortierung und Gruppierung je Anwender (`report_definitions`).
4. Filter sind strukturierte Bedingungen (Spalte, Operator, Wert, UND-verknüpft) aus einer festen Liste je Datenquelle. Freies SQL ist verboten.
5. Gruppierung: mehrere Ebenen mit Zwischensummen; je Gruppenebene ist wählbar, ob nur Summen oder alle Daten ausgegeben werden.
6. Gesamtsummen stehen immer in einer Zeile im Kopf der Auswertung.
7. Die Druckausgabe erfolgt als PDF ins Dokumentenarchiv.

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
| PDF | `reportlab` hinter einem Port der Anwendungsschicht |
| Übersetzung | Qt-Übersetzungsdateien (`qtbase_de`) für Standardschaltflächen; sie sind in das Paket aufzunehmen |

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
    application/ (services, reporting, ports)
    domain/ (services: reserve_rules, planning_rules, ...)
    infrastructure/
      database/ (models, repositories, migrations)
      reporting/ (PDF-Renderer)
      security/
    presentation/ (dialogs, view_models, widgets: FilterComboBox, DataTable, DayDateEdit)
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
| `cost_centers` | id, name, number, valid_from, kind (`STANDARD` / `WITHOUT_PLAN` / `INCOME`), income_mode (`PLAN` / `ACTUAL`, genau bei `INCOME` gesetzt), notes |
| `accounts` | id, name, number, account_type (`CHECKING`, `SAVINGS`, `INVESTMENT`, `RESERVE`), bank_name, owner_name, iban, cash_role (`NONE`, `CENTRAL_PAYMENT`, `OPERATING_FUNDS`; je Rolle höchstens ein Konto) |
| `booking_control` | id, is_active (genau ein aktiver Datensatz), planning_enabled, current_year, current_month, last_closed_year, last_closed_month |
| `period_closures` | id, year, month, closed_on, signature |
| `year_closures` | id, year, closed_on, signature |
| `closure_reopenings` | id, name, kind (`MONTH`/`YEAR`), year, month, reopened_on, reopened_by_user_id, reason, previous_signature, previous_closed_on, previous_closed_by_user_id, signature_was_valid |
| `account_opening_balances` | id, account_id (eindeutig), year, amount_cents (mit Vorzeichen); siehe 2.10 |
| `audit_log` | id, name (Aktion), entity, entity_id, user_id, old_value, new_value; enthält nie Passwörter oder Hashes |
| `user_settings` | id, name (Schlüssel, z. B. `booking_list.sort`), user_id, value_json; eindeutig je Anwender und Schlüssel |
| `report_definitions` | id, name, user_id, data_source, columns_json, filters_json, sort_json, grouping_json; eindeutig je Anwender und Name |
| `documents` | id, name, file_name, document_type, created_by_user_id, size_bytes, sha256 |
| `account_balance_checks` | id, account_id, year, month, expected_cents (mit Vorzeichen); eindeutig je Konto und Monat; siehe 2.13 |

Das erstmalige Passwort wird nur als Hash abgelegt. Es kann zurückgesetzt werden und erzwingt bei der ersten Anmeldung einen Wechsel.

### 4.3 Buchungsdaten

| Tabelle | Wesentliche Felder |
| --- | --- |
| `bookings` | id, name, origin_date (Entstehungsdatum), booking_date, booking_type (`COST_CENTER_TO_ACCOUNT`, `ACCOUNT_TO_ACCOUNT`, `BUDGET_TRANSFER`), entry_side (`DEBIT`/`CREDIT`), amount_cents (**mit Vorzeichen, ≠ 0**), merchant, booking_text, reversal_of_id, fiscal_year, fiscal_month, transfer_id (gemeinsame GUID der beiden Sätze einer Umbuchung, sonst leer) |
| `booking_legs` | id, booking_id, position (1 = führende Stelle, 2 = zweite Stelle), side (`DEBIT`/`CREDIT`), cost_center_id, account_id (genau eines von beiden) |

Regeln:

1. `amount_cents` ≠ 0, darf negativ sein.
2. Jede Buchung hat genau zwei Stellen (Zeilen in `booking_legs`). Bei `COST_CENTER_TO_ACCOUNT` stehen beide auf `entry_side`. Bei `ACCOUNT_TO_ACCOUNT` (nur Altbestand) und `BUDGET_TRANSFER` steht die führende Stelle auf `entry_side` und die zweite auf der gegenüberliegenden Seite. Bei `BUDGET_TRANSFER` tragen beide Stellen eine Kostenstelle und kein Konto.
3. Die Vorzeichen der Beträge werden nie normalisiert.
4. Löschen ist nur in einem offenen Monat zulässig und wird protokolliert; danach nur durch Minusbuchung.

### 4.4 Plandaten

| Tabelle | Wesentliche Felder |
| --- | --- |
| `cost_center_plans` | id, name, cost_center_id, year, base_budget_cents (Basisansatz, ≥ 0, nach Aktivierung fix), budget_transfer_cents (Projektion aus `BUDGET_TRANSFER`), reserve_carry_in_cents (manuell nur ohne Vorjahresplan, sonst aus dem Vorjahr abgeleitet), reserve_carry_out_cents (berechnet, siehe 2.12) |
| `monthly_plans` | id, name, cost_center_plan_id, month, plan_cents, reserve_plan_cents (Zuführung), reserve_is_manual (manuell gesetzte Zuführung), plan_mode (wird nicht mehr bedient, bleibt wegen der Signatur erhalten) |
| `monthly_actuals` | id, name, cost_center_id, year, month, debit_cents, credit_cents, reserve_actual_cents (Entlastung ist) |

`debit_cents` und `credit_cents` sind vorzeichenbehaftet und werden getrennt geführt. Die Ist-Bewegung ist `debit_cents − credit_cents`. `year` und `month` von `monthly_actuals` bezeichnen die **Planperiode** (Entstehungsdatum, siehe 2.11). `monthly_actuals` enthält ausschließlich Ist-Buchungen, nie Ansatzumbuchungen. Der wirksame Jahresansatz ist `base_budget_cents + budget_transfer_cents`; beides ist aus den Buchungen rekonstruierbar. Planung wird intern immer als Monatswerte gespeichert.

## 5. Kernabläufe

### 5.1 Anmeldung

1. Anwender meldet sich an der Login-Oberfläche an; es gibt nur diese eine Zugangsstufe.
2. Der Hash wird geprüft; bei Fehler erscheint eine neutrale Meldung.
3. Bei `must_change_password` ist nur der Passwortwechsel möglich.
4. Danach wird das Menü angezeigt.

### 5.2 Buchung erfassen

1. Kostenstelle gewählt: Haushaltsrestbetrag, Monatsplan und bisherige Rückstellung werden angezeigt.
2. Konto gewählt: aktueller Kontostand wird angezeigt.
3. Betrag wird in Soll **oder** Haben erfasst, Vorzeichen frei. Buchungs- und Entstehungsdatum werden als Tag oder vollständiges Datum erfasst (2.14).
4. Prüfung: Buchungszeitraum offen, Betrag ≠ 0, Buchungsart passend, Planjahr des Entstehungsdatums vorhanden und offen (2.11), Ansatzsperre (siehe 2.7). Bei Sperre wird die Ansatzumbuchung angeboten.
5. In **einer Transaktion**: Buchung, Buchungsseiten, Plan-Ist-Fortschreibung einschließlich Rückstellungsentlastung bzw. Ansatzfortschreibung, Audit-Eintrag.
6. Erfolg wird erst nach Commit gemeldet. Reicht die Rückstellung nicht aus, wird ein Hinweis gezeigt (2.12).

### 5.3 Monatsabschluss

1. Der Monat muss der älteste offene Monat sein.
2. Die Daten werden geprüft, das Abschlussdatum wird gesetzt und eine Signatur (SHA-256 über kanonisch serialisierte Buchungen des Monats, inklusive Vorzeichen und Seite) abgelegt.
3. Der Monat ist danach unveränderbar. `last_closed_month` und `current_month` werden fortgeschrieben.

Die Signatur macht nachträgliche Änderungen erkennbar; sie ersetzt keine rechtlich revisionssichere Archivierung. Sie wird über die Buchungsperiode gebildet; Ist-Buchungen mit Entstehungsdatum in einem abgeschlossenen Planmonat (2.11) verändern sie nicht.

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

Bereits entschieden und bestätigt: Planwerte in Soll-Richtung mit Basisansatz ≥ 0 (2.3; der wirksame Ansatz kann nach Regel 2a negativ werden), Monatsplan nur als Anzeige ohne Sperre (2.7), Trennung „Ansatzhöhe per Buchung, Verteilung in der Planung“ (2.8) und die Haushaltsreserve (2.9).

Mit Version 3 festgelegt (Entscheidungen E1–E7, Details in [ANALYSE_TESTERGEBNISSE_1.md](./ANALYSE_TESTERGEBNISSE_1.md), Abschnitt 4):

1. **Zwei Zeitachsen** (2.11): Plan-Ist nach Entstehungsdatum, Abschluss nach Buchungsdatum. Bei nicht buchbarem Planjahr erscheint ein Hinweisdialog je Buchung (E2).
2. **Rückstellungen** (2.12): virtuelles Konto je Kostenstelle, Soll = Bildung, Haben = Entlastung (E1), gesamter Jahresansatz wird verteilt (E6), Berechnung nach Monatssummen.
3. **Cash-Management** (2.13): erwarteter Kontostand je Konto und Monat (E3), geplante Ausgaben in zwei Spalten (E4).
4. **Auswertungen** (2.14): Datenquellen und Summierbarkeit von Spalten; PDF mit `reportlab` (E7).
5. **Kostenstellenart „ohne Plan“** bleibt bestehen (E5). Sie dient Konten bzw. Kostenstellen, die nicht von vornherein planbar sind, z. B. durchlaufende Posten.
6. **Einnahmen-Kostenstellen** (2.15): Kostenstellenart `INCOME` mit den Modi `PLAN` (verfügbar nach Plan) und `ACTUAL` (verfügbar nur nach Ist). Einnahmen werden geplant und gebucht und per Ansatzumbuchung weitergegeben.

Noch offen aus früheren Versionen:

1. **Planübertrag des Ansatzes:** Kontoanfangssalden sind in 2.10 geregelt, der Rückstellungsvortrag in 2.12. Offen bleibt der Planübertrag des Ansatzes.
2. **Weitere Kostenstellenarten:** neben `STANDARD`, `WITHOUT_PLAN` (Durchlaufposten u. Ä.) und `INCOME` (2.15) sind keine weiteren Arten vorgesehen; Bedarf wird bei Auftreten benannt.
3. **Mehrbenutzerbetrieb:** SQLite eignet sich für lokale Einzelplatznutzung. Bei paralleler Nutzung mehrerer Anwender ist ein Datenbankwechsel einzuplanen.
