/* ============================================================================
 *  Transatlantic Docs  ->  CMYK / PDF/X-3 (FOGRA39) mit PDFreactor
 * ----------------------------------------------------------------------------
 *  Erzeugt aus transatlantic-docs.html eine druckfertige PDF/X-3-Datei:
 *    - Device-CMYK-Farben (die HTML schaltet bei PDFreactor automatisch auf cmyk())
 *    - Output-Intent ISO Coated v2 (ECI) / FOGRA39
 *    - Beschnittzugabe ueber @page bleed (Body-Klasse bleed1/bleed3 in der HTML)
 *
 *  Voraussetzungen:
 *    npm i @realobjects/pdfreactor        (Node-Integration, lokaler Server)
 *    ICC-Profil "ISOcoated_v2_eci.icc"    (kostenlos: http://www.eci.org)
 *
 *  Aufruf:  node render-pdfx.js  transatlantic-docs.html  out.pdf
 *
 *  HINWEIS: Genau einmal mit echtem PDFreactor gegenpruefen
 *  (Acrobat-Preflight: PDF/X-3, Output-Intent FOGRA39, BleedBox = Trim + Beschnitt,
 *   Transparenzen geflattet). Werte ggf. an die PDFreactor-Version anpassen.
 * ========================================================================== */

const fs = require('fs');
const { PDFreactor } = require('@realobjects/pdfreactor');

const [, , inFile = 'transatlantic-docs.html', outFile = 'transatlantic-docs.pdf'] = process.argv;
const ICC = 'ISOcoated_v2_eci.icc';            // FOGRA39 / ISO Coated v2 (ECI)

// Soll die Engine zusaetzlich Schnittmarken zeichnen? Manche Druckereien
// wuenschen Crop-Marks zur Bleed-Flaeche; im Tool selbst ist die Option entfernt.
const WITH_CROP_MARKS = true;

(async () => {
  const pdfreactor = new PDFreactor();        // ggf. URL des PDFreactor-Webservice

  const config = {
    document: fs.readFileSync(inFile, 'utf8'),
    baseURL:  'file://' + process.cwd() + '/',

    // JavaScript MUSS aktiv sein: applyBrand() schaltet die Farben auf cmyk()
    javaScriptSettings: { enabled: true },

    // PDF/X-3
    conformance: PDFreactor.Conformance.PDFX3,

    // Farbraum: alle RGB-Eingaben in CMYK ueber das FOGRA39-Profil wandeln,
    // explizite cmyk()-Werte bleiben als Device-CMYK unveraendert erhalten.
    colorSpaceSettings: {
      targetColorSpace: PDFreactor.ColorSpace.CMYK,
      processColorProfile: { data: fs.readFileSync(ICC).toString('base64') }
    },

    // Output-Intent (Pflicht bei CMYK + PDF/X)
    outputIntentSettings: {
      identifier: 'FOGRA39',
      iccProfile: { data: fs.readFileSync(ICC).toString('base64') }
    },

    // Optional: Crop-Marks zusaetzlich zur (in der HTML definierten) Bleed-Flaeche.
    // Standard-CSS 'bleed' wird von Engines i.d.R. zusammen mit 'marks' wirksam.
    userStyleSheets: WITH_CROP_MARKS
      ? [{ content: '@page{ marks: crop; }' }]
      : [],

    addLinks: true,
    addBookmarks: true
  };

  try {
    const result = await pdfreactor.convert(config);
    fs.writeFileSync(outFile, Buffer.from(result.document, 'base64'));
    console.log('OK ->', outFile);
  } catch (e) {
    console.error('PDFreactor-Fehler:', e.message || e);
    process.exit(1);
  }
})();
