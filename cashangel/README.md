# Cash Angel – Haushalt im Blick

Analyse der eigenen Kontoauszüge: Wo geht das Geld jeden Monat hin, welche Abos laufen, welche
Gewohnheiten stecken dahinter. Läuft komplett lokal (FastAPI + SQLite + HTMX), keine Cloud, keine Telemetrie.
Technische Basis ist Steuerfuchs; Parser für CSV, CAMT.053 und PDF-Auszüge sind übernommen.

## Starten

- Voraussetzung: Python 3.10 oder neuer (`brew install python@3.12`). Das Apple-eigene python3 (3.9) reicht nicht;
  `start.sh` sucht selbst nach python3.12/3.13/3.11 und sagt Bescheid, wenn keins da ist.
- macOS: `Cash Angel.app` doppelklicken (oder ins Dock legen). Beim ersten Start wird einmalig eine
  virtuelle Umgebung angelegt und die Abhängigkeiten installiert (braucht einmal Internet, dauert ein paar
  Minuten; die App zeigt dazu eine Mitteilung). Nach einem neuen Download einmal Rechtsklick → Öffnen.
  Öffnet man die App direkt im frisch entpackten Ordner, startet macOS sie als Kopie aus einem Zufallsordner
  („App Translocation“); der Starter erkennt das, hebt die Quarantäne des Ordners auf und startet neu. Falls das
  nicht greift: `xattr -dr com.apple.quarantine ~/Downloads/cashangel` (Pfad anpassen) oder den Ordner im
  Finder einmal verschieben.
- Terminal: `./start.sh` – läuft auf http://127.0.0.1:8351
- Daten liegen in `~/CashAngel` (Datenbank `cashangel.db`, Konfiguration `kategorien.json`, Logs).
  Sichern heißt: diesen Ordner kopieren.
- Startet es nicht, nennt die Meldung der App die letzten Zeilen aus `~/CashAngel/server.log`; die
  Schritte der App selbst stehen in `~/CashAngel/app.log`. Im Terminal: `tail -n 40 ~/CashAngel/server.log`.

## Was es macht

1. **Import** – CSV-Export der Bank, CAMT.053 oder PDF-Kontoauszug (ING, Sparkasse, Volksbank, DKB, comdirect …).
   Mehrere Dateien auf einmal, bekannte Buchungen werden übersprungen, gelöschte kommen nicht zurück.
2. **Kategorisierung** – 30 Haushaltskategorien mit Erkennungsmustern (REWE → Lebensmittel, Netflix → Abos,
   congstar → Handy & Internet …). Gehälter werden den Personen zugeordnet („Gehalt Susanne“, „Gehalt Dustin“),
   Umbuchungen zwischen eigenen Konten zählen nicht. Reihenfolge: eigene IBAN → gelernte Zuordnung → Gehalt →
   Umbuchung → Muster (spezifischstes gewinnt) → Sonstiges. Eine Kategorie in der Buchungsliste ändern lernt
   die Zuordnung für denselben Empfänger.
3. **Übersicht** – Einnahmen, Ausgaben, Übrig und Sparquote im Monatsschnitt, Monatsbalken, Donut „Woher
   kommt das Geld“ (je Person) und „Wohin geht es“ (je Kategorie), Kategorienliste mit Anteilen.
   Sparpläne gelten als gespart, nicht als Ausgabe.
4. **Abos & Verträge** – wiederkehrende Zahlungen: gleicher Empfänger, regelmäßiger Abstand (wöchentlich bis
   jährlich), stabiler Betrag. Jahres- und Quartalsbeiträge auf den Monat umgerechnet, nächste Fälligkeit,
   „gekündigt“ oder „kein Abo“ markierbar.
5. **Sparpotenzial & Gewohnheiten** – Sparquote, Fixkostenquote, Abo-Summe, Latte-Faktor (Kleinbeträge),
   Wochenend-Anteil, Zahltag-Effekt (Ausgaben in den ersten zehn Tagen), Lieferdienste je Monat,
   Kategorien über dem Durchschnitt, Kauf-Serien, größte Einzelausgaben, häufigste Empfänger.
6. **Buchungen** – Volltextsuche, Filter nach Kategorie und Konto, Sortierung, Kategorie direkt in der Zeile,
   Mehrfachauswahl (Kategorie setzen, ausblenden, löschen), CSV-Export.

Der Zeitraum oben rechts (letzte 3/6/12 Monate, Jahr, einzelner Monat) gilt für alle Ansichten.

## Anpassen

`~/CashAngel/kategorien.json`: Personen, eigene IBANs, Kleinbetrag-Grenze, Kategorien mit Farbe, Fix/variabel
und Erkennungsmustern. Neue Standardmuster einer neuen Version werden beim Start ergänzt, eigene bleiben.

## Tests

```
python -m pytest -q
```
