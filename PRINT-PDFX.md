# Druck-Export – Transatlantic Docs (CMYK / PDF/X-3, FOGRA39)

## Überblick

| Zweck | Weg | Farbraum |
|---|---|---|
| Layout-/Inhaltskontrolle | Button **„PDF erzeugen"** im Tool (Browser) | RGB-Korrekturabzug, Trim 210×297 |
| **Produktive Druckdatei** | **PDFreactor** über `render-pdfx.js` | **CMYK, PDF/X-3, FOGRA39** |

Der Browser kann kein CMYK/PDF-X – deshalb läuft die produktive Ausgabe über PDFreactor.

## Schnellstart

```bash
npm i @realobjects/pdfreactor
# ICC-Profil "ISOcoated_v2_eci.icc" (ISO Coated v2 / FOGRA39) von eci.org neben das Skript legen
node render-pdfx.js transatlantic-docs.html out.pdf
```

## Wie die Farben gesteuert werden

Die HTML erkennt PDFreactor am User-Agent und gibt dann **Device-CMYK** statt HEX aus
(`applyBrand()` → `cmyk()`). Voraussetzung: **JavaScript im Export aktiviert**
(`javaScriptSettings.enabled = true`). Die CD-Werte (Styleguide S. 6) sind hinterlegt:

| Bereich | Primär (CMYK) | Pale (CMYK) |
|---|---|---|
| Transaroll – Bermuda | 80/10/20/10 | 50/0/20/0 |
| Transafix – Florida Keys | 70/0/40/0 | 40/0/30/0 |
| Transaflow – Baffin Bay | 75/0/0/0 | 50/0/0/0 |
| Transaplus – Baltic Storm | 40/40/0/22 | 20/20/0/10 |
| Headlines – Atlantic | 98/62/2/9 | – |

Der Deckblatt-Verlauf ist **vektorbasiert** (CSS-Verlauf Pale→Primär + SVG-Welle in Pale),
also auflösungsunabhängig und in jeder Größe scharf – kein DPI-Problem mehr.

## Beschnittzugabe

Im Tool wählbar: **Keine / 1 mm / 3 mm** (Body-Klasse `bleed1`/`bleed3`).
Die HTML definiert dazu `@page p1mm{bleed:1mm}` bzw. `@page p3mm{bleed:3mm}`; PDFreactor
schreibt daraus die **BleedBox** (TrimBox = 210×297). Randlose Flächen ziehen automatisch
über den Beschnitt.

## Beim ersten echten Export gegenprüfen (Acrobat-Preflight)

1. **PDF/X-3** konform, **Output-Intent = FOGRA39 / ISO Coated v2 (ECI)**.
2. **Markenfarben als Device-CMYK** (nicht über RGB konvertiert) – exakt die CD-Werte.
3. **BleedBox = TrimBox + Beschnitt** (bei 3 mm → 216×303). Falls die BleedBox ohne
   Schnittmarken nicht gesetzt wird: in `render-pdfx.js` `WITH_CROP_MARKS = true` lassen
   (Standard-CSS `bleed` wirkt je nach Engine-Version nur zusammen mit `marks`).
4. **Transparenzen geflattet** (Wellen-Deckkraft, Tabellen-Tints, Schatten) – PDF/X-3
   erlaubt keine lebende Transparenz; PDFreactor flattet beim X-3-Export.

> Die API-Schlüssel in `render-pdfx.js` ggf. an die eingesetzte PDFreactor-Version
> anpassen (Library vs. Web-Service-Client).
