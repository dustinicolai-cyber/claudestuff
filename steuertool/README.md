# Steuerfuchs – lokales Steuer- und Belegtool (§19 UStG, Anlage EÜR)

Ersetzt die handgepflegte Tabelle. Läuft komplett offline auf dem Mac, Daten bleiben
in `~/Steuertool/` (SQLite + Belegordner). Keine Cloud, keine Telemetrie.

## Start

**Steuerfuchs.app** in den Ordner-Inhalt schauen, ins Dock ziehen, anklicken. Die App startet
den Server im Hintergrund und öffnet den Browser; läuft er schon, öffnet sie nur den Browser.
Beenden über *Einstellungen → Steuerfuchs beenden*. Die App muss im Ordner `steuerfuchs`
liegen bleiben (sie startet das Programm daneben).

Alternativ im Finder **„Steuerfuchs starten.command“** doppelklicken (läuft sichtbar im Terminal). Beim ersten Mal blockiert macOS
eventuell („kann nicht geöffnet werden, da es von einem nicht verifizierten Entwickler stammt“):
dann Rechtsklick → **Öffnen** → nochmals **Öffnen**. Ab dann reicht der Doppelklick.

Oder im Terminal:

```bash
cd steuerfuchs
./start.sh          # legt .venv an, installiert einmalig Abhängigkeiten, öffnet den Browser
```

Danach läuft alles unter `http://127.0.0.1:8347`. Beenden mit Ctrl+C.
Einmalig braucht `start.sh` Netz für `pip install`; danach nicht mehr.

Voraussetzung: Python 3.12 (`brew install python@3.12`). Optional für Stufe 3/4 (OCR und
KI-Klassifizierung): [Ollama](https://ollama.com) mit `ollama pull qwen2.5vl:7b` und
`ollama pull qwen2.5:7b`. Ohne Ollama funktionieren E-Rechnung, PDF-Text, Regeln, Kontoauszüge
und alle Auswertungen trotzdem.

## Was wo liegt

| Datei / Ordner | Inhalt |
|---|---|
| `~/Steuertool/steuertool.db` | alle Buchungen, Kontobewegungen, Regeln |
| `~/Steuertool/Belege/<Jahr>/` | jede importierte Datei, umbenannt nach Datum |
| `~/Steuertool/steuerregeln.json` | **einzige Stelle** für Grenzwerte, Kategorien, EÜR-Zeilen, UStVA-Kennzahlen, Mail-Heuristik, Ollama-Modelle |
| `~/Steuertool/mail.json` | IMAP-Host/-Benutzer/-Ordner (kein Passwort – das liegt im Schlüsselbund) |

Sichern = diese Dateien kopieren. Pfad überschreibbar per `STEUERTOOL_HOME`.

## Ablauf

1. **Import** – Belege ins Feld ziehen. Pipeline: ZUGFeRD/XRechnung-XML (Konfidenz 1,0) →
   PDF-Textebene + Regex → Vision-OCR (nur Bilder/Scans, nur mit Ollama) → Klassifizierung
   (erst Regeln, dann Textmodell). Jede Datei zeigt, welche Stufe gegriffen hat.
2. **Prüfen** – Vorschläge nach Konfidenz, niedrigste zuerst. Beleg links, Felder rechts.
   `⏎` bestätigt und springt weiter, `Esc` überspringt. Jede Korrektur der Kategorie legt
   automatisch eine Regel für den Lieferanten an.
3. **Quartale** – Kategorien × Q1–Q4 + Jahr. Umschalter Brutto / Netto / USt / Abzugsfähig.
   Das Steuerjahr wird oben im Kopf gewählt und gilt für alle Ansichten.
   Die USt-Spalte ist der Was-wäre-wenn-Rechner: so viel Vorsteuer kostet §19 pro Quartal.
4. **Auswertung** – dieselben Zahlen als Diagramm, per Button umschaltbar: Quartale, Monate,
   Gewinnverlauf, Kategorien, Anteile, Tabelle.
5. **Offene Punkte** – Kontobewegungen ohne Beleg (wichtigste Liste), Mails „Rechnung manuell
   laden“, Belege ohne Kontobewegung (privat verauslagt / stornieren), mögliche Doppelbuchungen
   (zusammenführen / sind unterschiedlich). Bestätigte Buchungen werden nie gelöscht, nur storniert;
   jeder Eingriff steht im Protokoll am Ende des Belegjournals.
6. **Jahresabschluss** – Fragebogen gegen vergessene Posten, pro Frage Direkterfassung.
7. **Export** – Anlage EÜR (Zeile, Bezeichnung, Betrag – abtippfertig), UStVA je Quartal
   (nur §13b, Kz 46/47 bzw. 84/85), Quartalstabelle CSV/PDF, Belegjournal.

Kontoauszüge (CSV deutscher Banken oder CAMT.053) unter Import einlesen; Matching läuft
über Betrag exakt und Datum ±5 Tage.

## Steuerregeln im Code (Werte in `steuerregeln.json`)

- **§19**: kein Vorsteuerabzug, Brutto ist die Betriebsausgabe.
- **§13b Reverse-Charge** (Adobe, Figma, Google …): Erkennung über ausländische USt-IdNr,
  Hinweistext, bekannte Anbieter. 19 % auf den Nettobetrag werden als Zahllast (Kz 47) ausgewiesen.
- **Umsatzsteuer ans Finanzamt (EÜR Zeile 48)**: Standard ist das Abflussprinzip – Zeile 48 ist die
  Summe der tatsächlich überwiesenen Umsatzsteuer im Jahr. Überweisungen ans Finanzamt werden aus dem
  Kontoauszug erkannt (Kategorie „Umsatzsteuer ans Finanzamt gezahlt“), Erstattungen landen als
  Betriebseinnahme in Zeile 17, Einkommensteuer/Soli/Kirchensteuer sind privat. Unter Einstellungen
  lässt sich alternativ die rechnerische §13b-Steuer je Rechnung als Zeile 48 wählen; die Zahlungen
  zählen dann nicht doppelt. Die Quartalsübersicht zeigt entstandene und gezahlte Steuer nebeneinander.
- **Rückbuchungen**: Zahlung und Storno (gleicher Betrag, umgekehrtes Vorzeichen, gleicher Partner,
  ±14 Tage) werden im Abgleich als Paar markiert und lassen sich mit einem Klick beide ignorieren.
- **Bewirtung** 70 %, Warnung bei fehlendem Anlass/Teilnehmern.
- **GWG** bis 800 € netto Sofortabzug; darüber automatisch Anlagegut mit linearer,
  monatsgenauer AfA (Zeile 30).
- **Fahrtkosten** 0,30 €/km; **Homeoffice** 6 €/Tag, Deckel 1.260 €; **Privatanteil**
  Standard 50 %; **Geschenke** 50 € je Empfänger und Jahr (darüber komplett nicht abziehbar).

Die EÜR-Zeilennummern beziehen sich auf das Formular 2024/2025 und sollten jährlich
gegen das aktuelle Formular geprüft werden – nur in der JSON, kein Codeeingriff.

## Mail-Import

- **IMAP** strikt readonly (`select(readonly=True)` + `BODY.PEEK`): nichts wird als gelesen
  markiert, verschoben oder gelöscht. Passwort ausschließlich im macOS-Schlüsselbund.
  Gmail/iCloud: app-spezifisches Passwort.
- **Apple Mail lokal**: `~/Library/Mail` wird nach `.emlx` durchsucht, ohne Netz.
- Empfehlung: Mailregel, die Rechnungsmails in einen Ordner „Belege“ sortiert.
- PDF im Anhang → Pipeline (Duplikate via SHA-256). Nur ein Link → Liste „Rechnung manuell laden“.

## Entwicklung

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Grenzen

Kein Elster-Direktversand, keine Anlagenbuchhaltung über einfache AfA hinaus, kein Ersatz
für steuerliche Beratung. §13b und ein möglicher Wechsel zur Regelbesteuerung gehören
einmalig fachlich geprüft. Nichts wird ohne Bestätigung verbucht.
