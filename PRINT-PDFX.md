# Druck-Export – Transatlantic Docs

## Überblick

| Zweck | Weg | Ergebnis |
|---|---|---|
| **Druckdatei für die Druckerei** | Menü **„PDF erzeugen“ → „Druck-PDF für die Druckerei“** | CMYK, **PDF/X-4**, FOGRA39 / ISO Coated v2, mit Beschnitt |
| Korrekturabzug fürs Büro | Menü **„PDF erzeugen“ → „Korrektur-PDF fürs Büro“** | RGB über den Druckdialog des Browsers, ohne Beschnitt |

Das Druck-PDF erzeugt das Tool selbst – ohne Zusatzprogramm, ohne Installation, ohne Internet.
Es läuft in aktuellem Chrome oder Edge.

## Was im Druck-PDF steckt

- **Farben:** ausschließlich CMYK. Die Markenfarben kommen mit den exakten Werten aus dem
  Styleguide (S. 6) in die Datei, nicht über eine RGB-Umrechnung:

  | Bereich | Primär (CMYK) | Pale (CMYK) |
  |---|---|---|
  | Transaroll – Bermuda | 80/10/20/10 | 50/0/20/0 |
  | Transafix – Florida Keys | 70/0/40/0 | 40/0/30/0 |
  | Transaflow – Baffin Bay | 75/0/0/0 | 50/0/0/0 |
  | Transaplus – Baltic Storm | 40/40/0/22 | 20/20/0/10 |
  | Headlines – Atlantic | 98/62/2/9 | – |

- **Fließtext und graue Texte:** reines Schwarz (nur K, aufgerastert) statt vierfarbigem Grau –
  das bleibt im Druck scharf.
- **Tabellenzeilen und Linien:** Tonwerte von Atlantic (10 % bzw. 20 %).
- **Bilder und Piktogramme:** über das Profil ISO Coated v2 (FOGRA39) nach CMYK gewandelt,
  höchstens 300 dpi in der platzierten Größe.
- **Schrift:** DaxPro ist eingebettet; Text bleibt Text (durchsuchbar, markierbar).
- **Deckblatt:** Verlauf, Welle, Form und Logos sind Vektoren. Die Welle und der weiche Schatten
  unter der weißen Form nutzen Transparenz – in PDF/X-4 erlaubt.
- **Beschnitt:** die im Tool gewählte Beschnittzugabe (Keine / 1 mm / 3 mm). Bei 3 mm ist die Seite
  216 × 303 mm, das Endformat (TrimBox) 210 × 297 mm. Randlose Flächen laufen in den Beschnitt.
  Schnittmarken werden nicht gesetzt.
- **Ausgabebedingung:** FOGRA39, Profil „ISO Coated v2 (ECI)“ eingebettet.
- **Umbruch:** identisch zur Ansicht im Tool – jede Zeile steht dort, wo sie am Bildschirm steht.

## Vor der ersten Lieferung an die Druckerei prüfen (Acrobat Pro → Preflight)

1. Profil **„PDF/X-4-Konformität prüfen“** läuft ohne Fehler durch.
2. **Ausgabevorschau:** Markenfarben zeigen die Werte aus der Tabelle oben; Fließtext steht nur im
   Schwarzauszug.
3. **Seitenrahmen:** Endformat 210 × 297 mm, Anschnitt entsprechend der gewählten Zugabe.
4. **Schriften:** DaxPro eingebettet.

Das Tool wurde gegen zwei unabhängige PDF-Programme geprüft (Struktur, Farbräume, Schriften,
Seitenrahmen, Bildvergleich mit der Browser-Ansicht). Ein Preflight mit Acrobat ist damit nicht
ersetzt – er sollte einmal gemacht werden, bevor die erste Datei in Druck geht.

## Hinweise

- Zeichen, die es in der DaxPro nicht gibt (z. B. ⚠ oder ☑), werden als hochaufgelöste Maske in
  Textfarbe gesetzt. Pfeile (→) und Haken (✓) der Listen sind echte Schriftzeichen.
- Die Schrift wird vollständig eingebettet (nicht als Untergruppe). Die Schriftdatei erlaubt das
  Einbetten für Druck und Vorschau; ob die Lizenz das auch für diesen Einsatz abdeckt, bitte einmal
  mit dem Schrifthersteller klären.
- Das eingebettete Farbprofil „ISO Coated v2 (ECI)“ stammt unverändert von der European Color
  Initiative (www.eci.org).

## Alternative: PDFreactor (optional, ungetestet)

Der frühere Weg über die kommerzielle Engine PDFreactor liegt weiter bei (`render-pdfx.js`), wird
aber nicht mehr benötigt und wurde nie mit einer echten PDFreactor-Installation getestet:

```bash
npm i @realobjects/pdfreactor
# ICC-Profil "ISOcoated_v2_eci.icc" neben das Skript legen
node render-pdfx.js transatlantic-docs.html out.pdf MeinDokument.tadoc.json
```
