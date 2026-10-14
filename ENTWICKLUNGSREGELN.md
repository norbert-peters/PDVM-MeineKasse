# Meine Kasse – Entwicklungsregeln

Version 2. Diese Regeln sind für jeden Beitrag verbindlich. Fachliche Details stehen in der [Architekturvorgabe](./ARCHITEKTURVORGABE.md).

## 1. Allgemein

1. Anwendungssprache, Beschriftungen, Meldungen und Hilfetexte sind Deutsch.
2. Quellcode, Bezeichner, Tabellen und Spalten sind Englisch.
3. Neuer Code ist typisiert und durch Tests abgesichert.
4. Eine fachliche Regel wird genau einmal implementiert (Domain/Application), nicht in Dialogen dupliziert.
5. Änderungen sind klein, nachvollziehbar und getestet.

## 2. Datenbank und Datenzugriff

1. Alle Datenbankzugriffe erfolgen zentral über Repositories und eine gemeinsame Transaktionsverwaltung. SQL außerhalb von `infrastructure/database` ist verboten.
2. Jeder Datensatz hat eine GUID als Primärschlüssel (`id`) und einen `name`.
3. Verbindungen zwischen Datensätzen erfolgen ausschließlich über die GUID, nie über Name oder Nummer.
4. Schemaänderungen nur über Alembic-Migrationen; keine manuellen Eingriffe in produktive Dateien.
5. Fremdschlüssel sind je Verbindung aktiviert, SQL-Parameter sind immer gebunden.
6. Fachlich relevante Stammdaten werden deaktiviert statt gelöscht. Inaktive Stammdaten sind für neue Buchungen nicht mehr wählbar und in Listen standardmäßig ausgeblendet.
7. Jede Änderung an Stammdaten wird mit Anwender und geänderten Feldern im Audit-Protokoll festgehalten. Werte von IBAN und Anschrift werden dabei nie protokolliert, nur der Hinweis „(geändert)“.
8. Die Kostenstellenart (`STANDARD` / `WITHOUT_PLAN`) ist nach dem Anlegen fest, weil sie Planung und Ansatzsperre bestimmt. Nummern dürfen geändert werden, da Verbindungen über die GUID laufen, müssen aber eindeutig bleiben.
9. Ein Anwender kann sich nicht selbst deaktivieren, und es bleibt immer mindestens ein aktiver Anwender bestehen.

## 3. Beträge und Buchungen

1. Geldbeträge werden als ganzzahlige Cent **mit Vorzeichen** gespeichert und als `Decimal` verarbeitet. `float` ist verboten.
2. Positive und negative Beträge sind zulässig. Ein Betrag von 0 kann nicht gespeichert werden.
3. **Kein Seitentausch:** Ein negativer Betrag darf nie durch Vertauschen von Soll und Haben in einen positiven umgewandelt werden. Erfasstes Vorzeichen und erfasste Seite bleiben unverändert.
4. Ein Buchungssatz hat genau einen Betrag, entweder im Soll oder im Haben. Das wird in der Domain-Schicht geprüft, unabhängig von der Maske.
5. Soll- und Haben-Summen in Plan und Ist werden getrennt und mit Vorzeichen geführt. Die Bewegung ist `Soll − Haben`, der Saldo `Haben − Soll`.
6. Soll bedeutet bei Konto und Kostenstelle Abfluss bzw. Verbrauch, Haben Zufluss bzw. Verfügbares. Bei Ist-Buchungen (Kostenstelle → Konto) gilt die erfasste Seite gleichgerichtet für beide Stellen, es gibt keine Umkehr. Bei Konto → Konto und Ansatzumbuchung ist die zweite Stelle gegenläufig.
7. Korrekturen erfolgen durch Minusbuchung auf derselben Seite, verknüpft mit der Ursprungsbuchung. Nie durch Tausch der Seiten.
8. Prozentuale Teilbeträge behalten das Vorzeichen; Rundungsdifferenzen werden in Cent zugeordnet, sodass die Summe stimmt. Prozentwerte werden mit mindestens 3 Nachkommastellen geführt.
9. Eine Buchung wird nur in einem buchbaren Zeitraum gespeichert (aktueller Buchungsmonat, ein Monat davor und danach) und nur, wenn Monat und Jahr nicht abgeschlossen sind.
10. Buchung, Buchungsseiten, Audit-Eintrag und Soll-/Ist-Fortschreibung erfolgen in **einer** Transaktion. Scheitert ein Teil, wird alles zurückgerollt.
11. Plan-Ist-Werte und Salden müssen aus den Buchungen jederzeit neu aufgebaut werden können.
12. Eine Buchung ist erst mit dem Monatsabschluss unveränderbar. Bis dahin sind Änderungen erlaubt und werden protokolliert.
13. Es gibt genau drei Buchungsarten: Kostenstelle → Konto, Konto → Konto, Ansatz Kostenstelle → Ansatz Kostenstelle. Zulässige Kombinationen sind zentral definiert und getestet.
14. Konten und Kostenstellen werden nicht als Einnahme oder Ausgabe gekennzeichnet; das ergibt sich ausschließlich aus Seite und Vorzeichen der Buchungen.
15. Es gibt keine Sachkonten. Die Summe der Kontenbewegungen aus Ist-Buchungen muss der Summe der Ist-Bewegungen aller Kostenstellen entsprechen und wird automatisiert geprüft.
16. Eine Buchung kann bis zum Monatsabschluss geändert oder gelöscht werden. Dabei wird nicht „alt zurück, dann neu“, sondern die **Nettowirkung** gegen die Ansatzsperre geprüft. Eine stornierte Buchung und ein Storno sind nicht änderbar; ein Storno kann gelöscht werden.
17. Korrekturen in abgeschlossenen Monaten erfolgen durch Storno: eine Minusbuchung auf derselben Seite im offenen Zeitraum, verknüpft über `reversal_of_id`. Ein Storno kann nicht erneut storniert werden.
18. Neue Buchungen sind nur auf aktive Konten und Kostenstellen möglich; ein Storno darf auch auf inzwischen deaktivierte Stellen buchen.
19. Der Kontostand ist Anfangssaldo plus Bewegung (Haben − Soll). Ein Konto hat höchstens einen manuell erfassten Vortrag; folgende Jahre leiten ihn ab (siehe Architekturvorgabe 2.10).
20. Ein Vortrag ist nur editierbar, wenn das Konto kein Vorjahr hat und der Januar des Jahres nicht abgeschlossen ist. Auf ein Konto mit Vortrag wird nicht vor dem 01.01. des Vortragsjahres gebucht.
21. Anfangssalden gehen in die Signatur des Januar-Abschlusses ein. Ohne Anfangssalden darf sich die Signatur nicht ändern (Rückwärtskompatibilität der Abschlüsse).

## 4. Planung und Ansatzsperre

1. Planung wird intern immer als Monatswerte gespeichert. Quartals- und unregelmäßige Planung sind Eingabehilfen.
2. Plan und Ist verwenden dieselbe Vorzeichenkonvention, sodass der Abgleich ohne Umrechnung möglich ist. Der Jahresansatz ist immer ≥ 0.
3. Der Soll-/Ist-Abgleich erfolgt bei jeder Buchung und wird in den Plandaten festgehalten.
4. Der Basisansatz ist bei aktiver Planung fix. Seine Höhe ändert sich danach ausschließlich durch Ansatzumbuchungen (`BUDGET_TRANSFER`).
5. **Ansatzsperre:** Bei aktiver Planung wird eine Ist-Buchung auf einer `STANDARD`-Kostenstelle abgelehnt, wenn sie die Ist-Bewegung erhöht und der Haushaltsrest danach kleiner als 0 wäre. Entlastende Buchungen werden nie gesperrt. Die Prüfung erfolgt in der Domain-Schicht und in derselben Transaktion wie die Buchung.
6. Eine Ansatzumbuchung berührt weder Ist-Werte noch Konten. Sie ändert nur die wirksamen Jahresansätze, die Summe aller Ansätze bleibt gleich.
7. Der abgebende Ansatz darf nicht unter 0, nicht unter die Ist-Bewegung und nicht unter die Summe der Monatsplanwerte sinken.
8. Die Verteilung auf Monate, Quartale, unregelmäßige Beträge und Rückstellungen innerhalb des Jahresansatzes wird in der Planung geändert, nicht per Buchung. Die Summe der Monatsplanwerte darf den wirksamen Jahresansatz nicht überschreiten.
9. Planänderungen sind nur in offenen Monaten möglich und werden im Audit-Protokoll festgehalten.
10. Der Monatsplan sperrt nicht, Abweichungen werden nur angezeigt.
11. Kostenstellen der Art „ohne Plan“ unterliegen keiner Sperre und führen nur Soll- und Haben-Summen. Für sie gibt es keine Planung.
12. Die Summe der Monatsplanwerte darf den wirksamen Jahresansatz (Basisansatz + Ansatzumbuchungen) nicht übersteigen. Planwerte und Rückstellungsüberträge sind nie negativ.
13. Abgeschlossene Monate und Jahre sind in der Planung gesperrt. Ein unverändertes Speichern ist weiterhin möglich.
14. Quartals- und gleichmäßige Verteilung sind Eingabehilfen. Gespeichert werden immer Monatswerte, die Art (Monatlich, Quartal, Unregelmäßig, Rückstellung) ist nur eine Kennzeichnung.
15. Planänderungen werden mit den geänderten Feldern im Audit-Protokoll festgehalten.
16. Die Ist-Fortschreibung einer Kostenstelle richtet sich nach dem Entstehungsdatum (Planperiode), Konten, Abschlüsse und Signatur nach dem Buchungsdatum. Das Planjahr muss existieren und offen sein, sonst wird nicht gebucht (Architekturvorgabe 2.11).
17. Rückstellungen sind virtuell, werden in einer reinen Domain-Funktion aus Zuführungen, Vortrag und Monatssummen der Ist-Bewegung berechnet und sind nie negativ. Abgeschlossene Monate werden von der Berechnung nicht verändert.
18. Die Planungsart wird nicht mehr bedient; `plan_mode` bleibt wegen der Signatur unverändert im Schema.

## 4a. Abschluss

1. Der Monatsabschluss schließt immer den aktuellen Buchungsmonat und geht lückenlos nacheinander. Danach rückt der Buchungsmonat auf den Folgemonat, `last_closed_*` wird fortgeschrieben.
2. Vor dem Abschluss wird geprüft, ob die Ist-Fortschreibung und die Ansatzumbuchungen den Buchungen entsprechen. Bei Abweichungen wird nicht abgeschlossen.
3. Die Signatur ist ein SHA-256-Hash über die kanonisch serialisierten Buchungen (inklusive Ansatzumbuchungen, Seite, Vorzeichen, Stellen, Texte) und die Monatsplanwerte des Monats. Die Eingabereihenfolge darf das Ergebnis nicht verändern.
4. Der Jahresabschluss setzt zwölf abgeschlossene Monate mit noch gültigen Signaturen voraus. Seine Signatur bildet sich über die zwölf Monatssignaturen. Danach ist das ganze Jahr gesperrt.
5. Abgeschlossene Monate und Jahre werden nie verändert oder gelöscht. Die Integritätsprüfung berechnet alle Signaturen neu und meldet Abweichungen.
6. Das Standarddatum für neue Buchungen und Stornos liegt nie in einem abgeschlossenen Monat.
7. Die Signatur macht Änderungen erkennbar, sie ersetzt keine revisionssichere Archivierung und wird nicht als solche beworben.
8. Abschlüsse werden nur in umgekehrter Reihenfolge wiedereröffnet (siehe Architekturvorgabe 5.4). Eine Begründung ist Pflicht.
9. Jedes Wiedereröffnen wird dauerhaft in `closure_reopenings` dokumentiert (Anwender, Datum, Begründung, verworfene Signatur, Signatur zuvor gültig) und zusätzlich im Audit-Protokoll. Diese Einträge werden nie geändert oder gelöscht.
10. Eine ungültige Signatur verhindert das Wiedereröffnen nicht, wird aber vermerkt.
11. Nach dem Wiedereröffnen eines Monats springt der Buchungsmonat auf diesen Monat zurück, `last_closed_*` wird auf den vorherigen Abschluss zurückgesetzt.

## 5. Sicherheit und Datenschutz

1. Passwörter werden nur als Argon2id-Hash gespeichert, auch das erstmalige Passwort. Klartext ist verboten.
2. Das erstmalige Passwort und jeder administrative Reset setzen `must_change_password`. Der Wechsel ist bei der ersten Anmeldung zwingend.
3. Jede Passwortänderung aktualisiert `password_changed_at`.
4. Fehlermeldungen beim Login sind für falsche Anwender und falsche Passwörter identisch.
5. Passwörter, Hashes, IBAN und Anschriften erscheinen nicht in Logs oder Fehlermeldungen.
6. Die Produktivdatenbank und Sicherungen gehören nicht in die Versionsverwaltung.

## 6. Oberfläche

1. Währungsbeträge werden in Dialog und Auswertungen immer mit zwei Nachkommastellen und `€` angezeigt, z. B. `-1.234,56 €`.
2. Negative Beträge sind eindeutig erkennbar.
3. In der Buchungsmaske sperrt ein Betrag ≠ 0 in Soll oder Haben das jeweils andere Feld; bei 0 sind beide bedienbar.
4. Nach Auswahl der Kostenstelle werden Haushaltsrestbetrag, Monatsplan und bisherige Rückstellung angezeigt, nach Auswahl des Kontos der aktuelle Kontostand. Bei der Ansatzumbuchung wird der abgebbare Ansatz der Kostenstelle angezeigt.
5. Bei einer Ansatzsperre nennt die Meldung Haushaltsrest und fehlenden Betrag und bietet die Ansatzumbuchung an.
6. Offene und abgeschlossene Monate sind in Dialogen und Auswertungen erkennbar.
7. Fehlermeldungen nennen die konkrete Ursache.
8. Nach dem Login wird das Menü angezeigt.
9. Standardschaltflächen und Rückfragen sind deutsch (Ja/Nein). Auswahllisten sind per Texteingabe filterbar; dafür wird das gemeinsame Widget verwendet, kein eigener Combobox-Code in Dialogen.
10. Tabellen verwenden die gemeinsame Tabellenkomponente `DataTable` (Spaltenfilter, einstufige Sortierung nach Rohwerten, PDF-Ausgabe). Zellen sind `SortItem`; nach dem Füllen wird `apply()` aufgerufen. Die Sortierung wird je Anwender und Tabelle in `user_settings` gespeichert, nicht in `QSettings`. Eingabetabellen mit Zeilenbezug (Planung, Abschluss, Anfangssalden) sind ausgenommen.
11. Auswertungen verwenden nur Spalten und Filter aus einer festen Liste je Datenquelle (kein freies SQL). Summen werden nur über `ADDITIVE`-Spalten gebildet.
12. Erzeugte PDF-Dateien werden im Dokumentenarchiv registriert und von der Datensicherung erfasst. Dateinamen werden bereinigt (keine Pfadzeichen, höchstens 40 Zeichen manueller Zusatz).

## 7. Tests und Qualität

Mindestens automatisiert zu testen:

- positive und negative Beträge, Betrag 0, Soll/Haben-Exklusivität
- **kein Seitentausch**: ein negativer Soll-Betrag bleibt negativ im Soll
- Ist-Buchung wirkt gleichgerichtet auf Kostenstelle und Konto, Umbuchungen gegenläufig
- Kontrollsumme: Kontenbewegung aus Ist-Buchungen entspricht der Ist-Bewegung aller Kostenstellen
- Minusbuchung als Korrektur
- Wirkung auf Soll-Summe, Haben-Summe, Bewegung und Haushaltsrest bei positiven und negativen Beträgen
- prozentuale Aufteilung mit Vorzeichen und Rundungsausgleich
- Ansatzsperre: Buchung genau bis zum Rest erlaubt, ein Cent darüber gesperrt, entlastende und Minusbuchungen nie gesperrt, Kostenstelle „ohne Plan“ und inaktive Planung ungeprüft
- Ansatzumbuchung: Summe der Ansätze bleibt gleich, Ist und Konten bleiben unberührt, abgebender Ansatz nicht unter Ist-Bewegung oder verteilten Ansatz, negativer Betrag kehrt die Wirkung ohne Seitentausch um
- Planung: Summe der Monatswerte über dem Jahresansatz wird abgelehnt, Änderung in abgeschlossenem Monat gesperrt
- parallele Buchungen können die Ansatzsperre nicht umgehen
- Buchungszeitraum vor, im und nach dem erlaubten Fenster
- Sperre abgeschlossener Monate und Jahre, Monats- und Jahresabschluss mit Signatur
- Rollback bei fehlgeschlagener Plan-Ist-Fortschreibung
- Passwortwechsel beim ersten Login, Passwort-Reset
- Neuaufbau der Plan-Ist-Werte aus den Buchungen ergibt identische Werte

Tests verwenden ausschließlich synthetische Daten und eine temporäre SQLite-Datenbank. Lint-, Typ- und Testfehler blockieren die Abnahme.

## 8. Abnahme eines Funktionsbereichs

Ein Bereich ist fertig, wenn Regel und Verhalten in der Architekturvorgabe beschrieben sind, Eingabe, Validierung, Speicherung und Anzeige vollständig sind, Fehlerfälle behandelt werden, Tests und ggf. Migration vorliegen und keine Geheimnisse oder personenbezogenen Daten in Logs oder Versionsverwaltung gelangen.

## 9. Paketierung und Betrieb

1. Daten (Datenbank, Protokolle) liegen nie im Programmverzeichnis, sondern unter `%LOCALAPPDATA%\MeineKasse` bzw. im Pfad aus `MEINE_KASSE_DB`. Ein Update ersetzt nur das Programm.
2. Die Datenbank wird beim Start automatisch migriert. Neue Migrationen müssen als Dateien im Paket liegen (siehe `packaging\meine_kasse.spec`) und von `env.py` ohne zusätzliche Abhängigkeiten ladbar sein; Importe, die PyInstaller nicht erkennt, kommen als Hidden Import in die Spezifikation.
3. Unerwartete Fehler werden mit Stacktrace in `logs\meine_kasse.log` geschrieben (Rotation). Dem Anwender wird nur eine allgemeine Meldung mit dem Dateipfad gezeigt. Es werden nie Passwörter, Hashes oder Eingaben protokolliert.
4. Die Datensicherung erzeugt eine vollständige, geprüfte (`integrity_check`) Kopie über die SQLite-Sicherungsfunktion und überschreibt nie die laufende Datenbank.
5. Ein Paket wird erst ausgeliefert, wenn `packaging\build.ps1` fehlerfrei durchläuft. Dessen Smoke-Test führt `MeineKasse.exe --selbsttest` (temporäre Datenbank, nie die echten Daten) und einen Oberflächenstart mit Migrationsprüfung aus.
6. Neue Schichten, die im gepackten Programm fehlen könnten (Datenbank-Dialekte, native Bibliotheken, Migrationen), werden in den Selbsttest aufgenommen.
