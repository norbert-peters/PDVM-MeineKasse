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
6. Fachlich relevante Stammdaten werden deaktiviert statt gelöscht.

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
11. Kostenstellen der Art „ohne Plan“ unterliegen keiner Sperre und führen nur Soll- und Haben-Summen.

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
