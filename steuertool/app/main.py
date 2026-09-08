"""FastAPI-Server. Bindet nur an 127.0.0.1, keine externen Aufrufe außer dem
lokalen Ollama. Alle Ansichten sind HTMX-Fragmente unter /ui/*, alle Aktionen unter /api/*.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from sqlmodel import Session, select

from . import config, export, matching, ollama, regeln as regelwerk, steuerlogik, ui
from .db import get_session, init_db, kategorien_synchronisieren
from .importer import klassifizierung, kontoauszug, mail, pipeline
from .models import Anlagegut, Beleg, Buchung, DedupIgnoriert, Fragebogen, IgnorRegel, Kategorie, Kontobewegung, MailFund, Protokoll, Regel

@asynccontextmanager
async def _lebenszyklus(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Steuerfuchs", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lebenszyklus)
STATIC = config.APP_DIR / "static"
KI_AN = {"wert": True}




# ------------------------------------------------------------ Hilfen

def _kats(s: Session) -> dict[int, Kategorie]:
    return {k.id: k for k in s.exec(select(Kategorie).where(Kategorie.aktiv == True)).all()}  # noqa: E712


def _kat_liste(s: Session) -> list[Kategorie]:
    return sorted(_kats(s).values(), key=lambda k: (0 if k.richtung == "einnahme" else 1, k.name))


def _jahre(s: Session) -> list[int]:
    jahre = {b.datum.year for b in s.exec(select(Buchung)).all()} | {k.datum.year for k in s.exec(select(Kontobewegung)).all()} | {date.today().year}
    return sorted(jahre, reverse=True)


def _standardjahr(s: Session) -> int:
    """Jüngstes Jahr mit Daten (Buchungen oder Kontobewegungen) – im Frühjahr ist das meist das Vorjahr."""
    jahre = [b.datum.year for b in s.exec(select(Buchung)).all()] + [k.datum.year for k in s.exec(select(Kontobewegung)).all()]
    return max(jahre) if jahre else date.today().year


def _aktive(s: Session) -> list[Buchung]:
    return [b for b in s.exec(select(Buchung)).all() if not b.storniert]


def _offene(s: Session) -> list[Buchung]:
    return s.exec(select(Buchung).where(Buchung.status == "vorschlag").order_by(Buchung.konfidenz, Buchung.datum)).all()


def _html(inhalt: str) -> HTMLResponse:
    return HTMLResponse(inhalt)


def _f(v: Optional[str]) -> float:
    if v is None or str(v).strip() == "":
        return 0.0
    return float(str(v).replace(",", "."))


def _meta_aus_form(form) -> dict:
    m = {}
    for k in ("anlass", "teilnehmer", "km", "tage", "empfaenger", "privatanteil_prozent", "nutzungsdauer_jahre"):
        v = form.get(f"meta_{k}")
        if v not in (None, ""):
            m[k] = v
    return m


def _buchung_aus_form(b: Buchung, form) -> None:
    b.datum = date.fromisoformat(form["datum"]) if form.get("datum") else b.datum
    b.richtung = form.get("richtung", "ausgabe")
    b.lieferant = form.get("lieferant", "").strip()
    b.beschreibung = form.get("beschreibung", "").strip()
    b.rechnungsnummer = form.get("rechnungsnummer", "").strip()
    b.ust_idnr = form.get("ust_idnr", "").replace(" ", "").upper()
    netto, satz, ust, brutto = _f(form.get("betrag_netto")), _f(form.get("ust_satz")), _f(form.get("ust_betrag")), _f(form.get("betrag_brutto"))
    if brutto and not netto:
        netto, satz, ust, brutto = steuerlogik.betraege_vervollstaendigen(None, satz, None, brutto)
    elif netto and not brutto:
        netto, satz, ust, brutto = steuerlogik.betraege_vervollstaendigen(netto, satz, None, None)
    b.betrag_netto, b.ust_satz, b.ust_betrag, b.betrag_brutto = round(netto, 2), satz, round(ust, 2), round(brutto, 2)
    b.kategorie_id = int(form["kategorie_id"]) if form.get("kategorie_id") else None
    b.reverse_charge = form.get("reverse_charge") == "1"
    alt = json.loads(b.meta_json or "{}")
    alt.update(_meta_aus_form(form))
    b.meta_json = json.dumps(alt, ensure_ascii=False)


def _bewertung(s: Session, b: Buchung) -> steuerlogik.Bewertung:
    kats = _kats(s)
    k = kats.get(b.kategorie_id or -1)
    alle = s.exec(select(Buchung)).all()
    ctx = steuerlogik.jahres_kontext(alle, kats, b.datum.year, ausser_id=b.id)
    return steuerlogik.bewerte(b, k, config.regeln(), ctx)


def _bestaetigen(s: Session, b: Buchung, vorher_kat: Optional[int], vorher_weg: str) -> steuerlogik.Bewertung:
    """Kernschritt der Review-Pflicht: Sonderregeln anwenden, Regel lernen, ggf. AfA anlegen."""
    cfg = config.regeln()
    kats = _kats(s)
    bw = _bewertung(s, b)
    if bw.umwandeln_in:
        ziel = next((k for k in kats.values() if k.schluessel == bw.umwandeln_in), None)
        if ziel:
            b.kategorie_id = ziel.id
    k = kats.get(b.kategorie_id or -1)
    if k and k.sonderfall == "afa":
        vorhanden = s.exec(select(Anlagegut).where(Anlagegut.buchung_id == b.id)).first()
        nd = int(json.loads(b.meta_json or "{}").get("nutzungsdauer_jahre") or cfg["afa_nutzungsdauer_standard_jahre"])
        if not vorhanden:
            s.add(Anlagegut(buchung_id=b.id, bezeichnung=(b.beschreibung or b.lieferant or "Wirtschaftsgut")[:80],
                            anschaffung=b.datum, anschaffungskosten=b.betrag_brutto if cfg["kleinunternehmer"] else b.betrag_netto,
                            nutzungsdauer_jahre=nd))
        else:
            vorhanden.anschaffungskosten = b.betrag_brutto if cfg["kleinunternehmer"] else b.betrag_netto
            vorhanden.anschaffung = b.datum
            vorhanden.nutzungsdauer_jahre = nd
            s.add(vorhanden)
    b.eur_zeile = bw.eur_zeile
    b.hinweise_json = json.dumps(bw.hinweise + [f"⚠ {w}" for w in bw.warnungen], ensure_ascii=False)
    b.status = "bestaetigt"
    b.bestaetigt_am = datetime.now()
    b.konfidenz = 1.0
    # Regel lernen: bei Korrektur immer, bei KI-/Fallback-Vorschlag auch beim Bestätigen
    if b.lieferant and b.kategorie_id and k and k.schluessel not in ("anlagevermoegen",):
        korrigiert = vorher_kat != b.kategorie_id
        if korrigiert or vorher_weg.startswith(("ki:", "fallback")):
            r = regelwerk.regel_aus_korrektur(s, b.lieferant, b.kategorie_id)
            if r and not korrigiert:
                r.erstellt_aus_korrektur = False
                s.add(r)
    s.add(b)
    s.commit()
    return bw


# ------------------------------------------------------------ Seiten

KEIN_CACHE = {"Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache"}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__VERSION__", config.version())
    return HTMLResponse(html, headers=KEIN_CACHE)


@app.get("/static/{name}")
def static(name: str):
    p = STATIC / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, headers=KEIN_CACHE)


@app.get("/api/version")
def api_version() -> JSONResponse:
    return JSONResponse({"version": config.version()})


def _nav_counts(s: Session, jahr: int) -> dict:
    """Einmal pro Request: alles, was die Navigation anzeigen soll."""
    op = matching.offene_punkte(s)
    funde = s.exec(select(MailFund).where(MailFund.status == "offen")).all()
    fragen = config.regeln()["jahresabschluss_fragen"]
    erledigt = sum(1 for f in s.exec(select(Fragebogen).where(Fragebogen.jahr == jahr)).all() if f.erledigt)
    return {"vorschlaege": len(_offene(s)), "beleg_fehlt": len(op["ohne_beleg"]), "manuell_holen": len(funde),
            "offen_gesamt": len(op["ohne_beleg"]) + len(funde) + len(op["ohne_konto"]) + len(op["doppel"]),
            "jahresabschluss": {"erledigt": erledigt, "gesamt": len(fragen)}}


@app.get("/api/status")
def status(jahr: Optional[int] = None, s: Session = Depends(get_session)) -> JSONResponse:
    jahr = jahr or _standardjahr(s)
    ki = ollama.status(config.regeln(), KI_AN["wert"])
    return JSONResponse({**_nav_counts(s, jahr), "ki": ki, "ollama": ki == "aktiv", "jahre": _jahre(s), "standardjahr": _standardjahr(s), "jahr": jahr})


@app.get("/beleg/{beleg_id}/datei")
def beleg_datei(beleg_id: int, s: Session = Depends(get_session)):
    b = s.get(Beleg, beleg_id)
    if not b or not Path(b.dateipfad).exists():
        raise HTTPException(404)
    return FileResponse(b.dateipfad, media_type=b.mime or None, filename=b.original_name,
                        content_disposition_type="inline")


# ------------------------------------------------------------- Import

@app.get("/ui/import", response_class=HTMLResponse)
def ui_import() -> HTMLResponse:
    return _html(ui.import_view(ollama.verfuegbar(config.regeln()), KI_AN["wert"]))


@app.post("/api/import", response_class=HTMLResponse)
async def api_import(datei: UploadFile = File(...), ki: str = Form("1"), richtung: str = Form("ausgabe"),
                     s: Session = Depends(get_session)) -> HTMLResponse:
    KI_AN["wert"] = ki == "1"
    richtung = "einnahme" if richtung == "einnahme" else "ausgabe"
    daten = await datei.read()
    try:
        erg = pipeline.importiere_datei(s, daten, datei.filename or "beleg", herkunft="upload", ki_erlaubt=KI_AN["wert"], richtung=richtung)
    except Exception as ex:  # Fehler pro Datei anzeigen, nicht den Import abbrechen
        erg = pipeline.ImportErgebnis(status="fehler", meldung=str(ex))
    return _html(ui.import_zeile(datei.filename or "beleg", erg, richtung))


@app.post("/api/import/ordner", response_class=HTMLResponse)
def api_import_ordner(pfad: str = Form(...), ki: str = Form("1"), richtung: str = Form("ausgabe"), s: Session = Depends(get_session)) -> HTMLResponse:
    p = Path(pfad).expanduser()
    if not p.is_dir():
        return _html(ui.meldung_box(f"Kein Ordner: {p}", "fehler-box"))
    zeilen = []
    for f in sorted(p.iterdir()):
        if f.is_file() and f.suffix.lower() in {".pdf", ".xml"} | pipeline.BILD_ENDUNGEN:
            try:
                erg = pipeline.importiere_pfad(s, f, herkunft="ordner", ki_erlaubt=ki == "1", richtung=richtung)
            except Exception as ex:
                erg = pipeline.ImportErgebnis(status="fehler", meldung=str(ex))
            zeilen.append(ui.import_zeile(f.name, erg, richtung))
    return _html(f'<table class="tabelle"><thead><tr><th>Datei</th><th>Art</th><th>Status</th><th>Stufe</th><th>Konfidenz</th><th>Meldung</th></tr></thead><tbody>{"".join(zeilen) or "<tr><td colspan=6 class=muted>Keine passenden Dateien.</td></tr>"}</tbody></table>')


@app.post("/api/konto/import", response_class=HTMLResponse)
async def api_konto_import(datei: UploadFile = File(...), s: Session = Depends(get_session)) -> HTMLResponse:
    daten = await datei.read()
    bewegungen = kontoauszug.lese_kontoauszug(daten, datei.filename or "")
    if not bewegungen:
        return _html(ui.meldung_box("Keine Buchungen erkannt – Spalten Datum/Betrag nicht gefunden.", "fehler-box"))
    neu, dup = matching.kontobewegungen_speichern(s, bewegungen, datei.filename or "")
    ign = matching.ignorregeln_anwenden(s)
    treffer = matching.matche(s)
    meldung = (f"{neu} neue Kontobewegungen eingelesen ({dup} bereits bekannt), {treffer} automatisch einer Rechnung zugeordnet, "
               f"{ign} per Regel ignoriert.")
    jahr = max((b.datum.year for b in bewegungen), default=None)
    return _html(ui.meldung_box(meldung) + ui_abgleich(jahr, "offen", s).body.decode())


# ------------------------------------------------------------- Prüfen

def _reiter(richtung: Optional[str], offene: list[Buchung]) -> str:
    if richtung in ("einnahme", "ausgabe"):
        return richtung
    return "einnahme" if offene and all(x.richtung == "einnahme" for x in offene) else "ausgabe"


@app.get("/ui/pruefen", response_class=HTMLResponse)
def ui_pruefen(ueberspringen: Optional[int] = None, richtung: Optional[str] = None, s: Session = Depends(get_session)) -> HTMLResponse:
    offene = _offene(s)
    reiter = _reiter(richtung, offene)
    im_reiter = [x for x in offene if x.richtung == reiter]
    if not im_reiter:
        zaehler = {"einnahme": sum(1 for x in offene if x.richtung == "einnahme"), "ausgabe": sum(1 for x in offene if x.richtung == "ausgabe")}
        return _html(ui.pruefen_leer(reiter, zaehler))
    b = next((x for x in im_reiter if x.id != ueberspringen), im_reiter[0])
    return _pruefen_detail(s, b, reiter)


@app.get("/ui/pruefen/{buchung_id}", response_class=HTMLResponse)
def ui_pruefen_id(buchung_id: int, s: Session = Depends(get_session)) -> HTMLResponse:
    b = s.get(Buchung, buchung_id)
    if not b:
        raise HTTPException(404)
    return _pruefen_detail(s, b, b.richtung)


def _pruefen_detail(s: Session, b: Buchung, reiter: Optional[str] = None) -> HTMLResponse:
    beleg = s.get(Beleg, b.beleg_id) if b.beleg_id else None
    try:
        extraktion = json.loads(b.extraktion_json or "{}")
    except json.JSONDecodeError:
        extraktion = {}
    offene = _offene(s)
    reiter = reiter or b.richtung
    zaehler = {"einnahme": sum(1 for x in offene if x.richtung == "einnahme"), "ausgabe": sum(1 for x in offene if x.richtung == "ausgabe")}
    liste = [x for x in offene if x.richtung == reiter]
    if b.status != "vorschlag" or b.id not in {x.id for x in liste}:
        liste = [b] + liste
    return _html(ui.pruefen_view(b, beleg, _kat_liste(s), liste, _bewertung(s, b), extraktion, config.regeln(), reiter, zaehler))


@app.get("/ui/manuell", response_class=HTMLResponse)
def ui_manuell(s: Session = Depends(get_session)) -> HTMLResponse:
    b = Buchung(datum=date.today(), ust_satz=config.regeln()["regelsteuersatz"])
    return _html(ui.manuell_view(b, _kat_liste(s), config.regeln()))


@app.post("/api/buchung/{buchung_id}/bestaetigen", response_class=HTMLResponse)
async def api_bestaetigen(buchung_id: int, request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    b = s.get(Buchung, buchung_id)
    if not b:
        raise HTTPException(404)
    form = await request.form()
    vorher_kat, vorher_weg = b.kategorie_id, b.klassifizierung_weg or ""
    _buchung_aus_form(b, form)
    if not b.kategorie_id:
        return _pruefen_detail(s, b)
    reiter = b.richtung
    _bestaetigen(s, b, vorher_kat, vorher_weg)
    matching.matche(s)
    return ui_pruefen(None, reiter, s)


@app.post("/api/buchung/neu", response_class=HTMLResponse)
async def api_buchung_neu(request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    form = await request.form()
    b = Buchung(datum=date.today(), extraktion_stufe="manuell", klassifizierung_weg="manuell")
    _buchung_aus_form(b, form)
    if not b.kategorie_id:
        return _html(ui.meldung_box("Kategorie fehlt – Buchung nicht gespeichert.", "fehler-box"))
    s.add(b)
    s.commit()
    s.refresh(b)
    _bestaetigen(s, b, b.kategorie_id, "manuell")
    matching.matche(s)
    zurueck = form.get("zurueck", "")
    if zurueck.startswith("jahresabschluss:"):
        return ui_jahresabschluss(int(zurueck.split(":")[1]), s)
    return _html(ui.meldung_box(f"Buchung #{b.id} erfasst: {b.lieferant} {export.eur_fmt(b.betrag_brutto)}.") +
                 ui.manuell_view(Buchung(datum=b.datum, ust_satz=b.ust_satz, richtung=b.richtung), _kat_liste(s), config.regeln()))


def _buchung_loeschen(s: Session, b: Buchung) -> None:
    """Buchung samt Beleg-Eintrag entfernen. Die Datei wandert in Belege/Papierkorb,
    damit nichts verloren geht und ein erneuter Import nicht als Duplikat abgewiesen wird."""
    for k in s.exec(select(Kontobewegung).where(Kontobewegung.buchung_id == b.id)).all():
        k.buchung_id = None
        s.add(k)
    for a in s.exec(select(Anlagegut).where(Anlagegut.buchung_id == b.id)).all():
        s.delete(a)
    if b.beleg_id:
        beleg = s.get(Beleg, b.beleg_id)
        andere = s.exec(select(Buchung).where(Buchung.beleg_id == b.beleg_id, Buchung.id != b.id)).first()
        if beleg and not andere:
            quelle = Path(beleg.dateipfad)
            if quelle.exists():
                papierkorb = config.beleg_dir() / "Papierkorb"
                papierkorb.mkdir(parents=True, exist_ok=True)
                ziel = papierkorb / quelle.name
                n = 1
                while ziel.exists():
                    ziel = papierkorb / f"{quelle.stem}_{n}{quelle.suffix}"
                    n += 1
                try:
                    quelle.rename(ziel)
                except OSError:
                    pass
            s.delete(beleg)
    s.delete(b)


@app.post("/api/buchung/{buchung_id}/loeschen", response_class=HTMLResponse)
def api_buchung_loeschen(buchung_id: int, s: Session = Depends(get_session)) -> HTMLResponse:
    b = s.get(Buchung, buchung_id)
    if b:
        reiter = b.richtung
        _buchung_loeschen(s, b)
        s.commit()
        return ui_pruefen(None, reiter, s)
    return ui_pruefen(None, None, s)


def _neu_erkennen(s: Session, b: Buchung) -> bool:
    """Extraktion auf der gespeicherten Belegdatei wiederholen, Vorschlag aktualisieren."""
    if b.status != "vorschlag" or not b.beleg_id:
        return False
    beleg = s.get(Beleg, b.beleg_id)
    if not beleg or not Path(beleg.dateipfad).exists():
        return False
    cfg = config.regeln()
    daten = Path(beleg.dateipfad).read_bytes()
    stufe, felder, text = pipeline.extrahiere(daten, beleg.original_name or Path(beleg.dateipfad).name, cfg, KI_AN["wert"])
    if stufe == "keine":
        return False
    netto, satz, ust, brutto = steuerlogik.betraege_vervollstaendigen(
        felder.get("betrag_netto"), felder.get("ust_satz"), felder.get("ust_betrag"), felder.get("betrag_brutto"))
    lieferant = (felder.get("lieferant") or b.lieferant or "").strip()
    rc, gruende = steuerlogik.erkenne_reverse_charge(text or felder.get("volltext", ""), felder.get("ust_idnr", ""), lieferant, ust, cfg)
    if felder.get("reverse_charge_hinweis") and ust == 0:
        rc = True
    if rc and satz == 0 and netto == 0 and brutto:
        netto = brutto
    b.datum = felder.get("datum") or b.datum
    b.betrag_netto, b.ust_satz, b.ust_betrag, b.betrag_brutto = netto, satz, ust, brutto
    b.lieferant, b.rechnungsnummer = lieferant, felder.get("rechnungsnummer") or b.rechnungsnummer
    b.ust_idnr = felder.get("ust_idnr") or b.ust_idnr
    b.reverse_charge = rc
    b.extraktion_stufe = stufe
    b.konfidenz = round(min(felder.get("konfidenz", 0.0), 1.0) * 0.7 + (0.95 if b.klassifizierung_weg.startswith("regel") else 0.3) * 0.3, 2)
    b.extraktion_json = json.dumps({k: v for k, v in felder.items() if k != "volltext"}, default=str, ensure_ascii=False)
    b.hinweise_json = json.dumps(gruende + (["Kein Betrag erkannt."] if not brutto else []), ensure_ascii=False)
    beleg.quelle = stufe
    s.add(beleg)
    s.add(b)
    return True


@app.post("/api/buchung/{buchung_id}/neu-erkennen", response_class=HTMLResponse)
def api_neu_erkennen(buchung_id: int, s: Session = Depends(get_session)) -> HTMLResponse:
    b = s.get(Buchung, buchung_id)
    if not b:
        raise HTTPException(404)
    ok = _neu_erkennen(s, b)
    s.commit()
    s.refresh(b)
    antwort = _pruefen_detail(s, b)
    if not ok:
        return _html(ui.meldung_box("Neu erkennen nicht möglich (bereits bestätigt, Datei fehlt oder keine Stufe greift).", "warn-box") + antwort.body.decode())
    return antwort


@app.post("/api/buchungen/neu-erkennen", response_class=HTMLResponse)
async def api_buchungen_neu_erkennen(request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    form = await request.form()
    ids = [int(x) for x in form.getlist("ids") if str(x).isdigit()]
    n = 0
    for bid in ids:
        b = s.get(Buchung, bid)
        if b and _neu_erkennen(s, b):
            n += 1
    s.commit()
    return _html(ui.meldung_box(f"{n} von {len(ids)} Vorschlägen neu erkannt.") + ui_pruefen(None, None, s).body.decode())


@app.post("/api/buchungen/loeschen", response_class=HTMLResponse)
async def api_buchungen_loeschen(request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    """Sammel-Löschen aus der Prüfliste (Checkboxen)."""
    form = await request.form()
    ids = [int(x) for x in form.getlist("ids") if str(x).isdigit()]
    n = 0
    for bid in ids:
        b = s.get(Buchung, bid)
        if b:
            _buchung_loeschen(s, b)
            n += 1
    s.commit()
    antwort = ui_pruefen(None, None, s)
    return _html(ui.meldung_box(f"{n} Buchungen gelöscht. Belegdateien liegen in Belege/Papierkorb.") + antwort.body.decode())


# ------------------------------------------------------------ Quartale

def _uebersicht(s: Session, jahr: int) -> dict:
    return steuerlogik.quartalsuebersicht(_aktive(s), _kats(s), s.exec(select(Anlagegut)).all(), jahr, config.regeln())


@app.get("/ui/quartale", response_class=HTMLResponse)
def ui_quartale(jahr: Optional[int] = None, modus: str = "brutto", s: Session = Depends(get_session)) -> HTMLResponse:
    jahr = jahr or _standardjahr(s)
    if modus not in ("brutto", "netto", "ust", "abzugsfaehig"):
        modus = "brutto"
    anlagen = s.exec(select(Anlagegut).where(Anlagegut.aktiv == True)).all()  # noqa: E712
    return _html(ui.quartale_view(_uebersicht(s, jahr), modus, _jahre(s), len(_offene(s)), anlagen))


@app.post("/api/anlage/{anlage_id}", response_class=HTMLResponse)
def api_anlage(anlage_id: int, nutzungsdauer_jahre: int = Form(...), jahr: int = Form(...), s: Session = Depends(get_session)) -> HTMLResponse:
    a = s.get(Anlagegut, anlage_id)
    if a:
        a.nutzungsdauer_jahre = max(1, nutzungsdauer_jahre)
        s.add(a)
        s.commit()
    return ui_quartale(jahr, "brutto", s)


# ------------------------------------------------------------ Auswertung

@app.get("/ui/auswertung", response_class=HTMLResponse)
def ui_auswertung(jahr: Optional[int] = None, s: Session = Depends(get_session)) -> HTMLResponse:
    jahr = jahr or _standardjahr(s)
    return _html(ui.auswertung_view(jahr, _jahre(s)))


@app.get("/api/auswertung")
def api_auswertung(jahr: int, s: Session = Depends(get_session)) -> JSONResponse:
    ue = _uebersicht(s, jahr)
    kategorien = [{"name": r["kategorie"].name, "richtung": r["kategorie"].richtung, "brutto": round(r["jahr"].brutto, 2),
                   "abzugsfaehig": round(r["jahr"].abzugsfaehig, 2), "ust": round(r["jahr"].ust, 2), "anzahl": r["jahr"].anzahl}
                  for r in ue["zeilen"]]
    return JSONResponse({
        "jahr": jahr,
        "quartale": [{"q": i + 1, "einnahmen": round(ue["einnahmen"][i].abzugsfaehig, 2), "ausgaben": round(ue["ausgaben"][i].abzugsfaehig, 2),
                      "gewinn": ue["gewinn"][i], "ust": ue["entgangene_vorsteuer"][i]} for i in range(4)],
        "jahr_summe": {"einnahmen": round(ue["einnahmen"][4].abzugsfaehig, 2), "ausgaben": round(ue["ausgaben"][4].abzugsfaehig, 2),
                       "gewinn": ue["gewinn"][4], "ust": ue["entgangene_vorsteuer"][4]},
        "monate": ue["monate"],
        "kategorien": kategorien,
    })


# ------------------------------------------------------------ Abgleich

def _buchung_aus_konto(s: Session, k: Kontobewegung) -> Buchung:
    """Buchungsvorschlag aus einer Kontobewegung (Beleg fehlt) – Kategorie per Regel, sonst offen."""
    cfg = config.regeln()
    richtung = "ausgabe" if k.betrag < 0 else "einnahme"
    brutto = abs(k.betrag)
    netto, satz, ust, brutto = steuerlogik.betraege_vervollstaendigen(None, 0.0 if richtung == "einnahme" else cfg["regelsteuersatz"], None, brutto)
    b = Buchung(datum=k.datum, richtung=richtung, betrag_netto=netto, ust_satz=satz, ust_betrag=ust, betrag_brutto=brutto,
                lieferant=k.gegenkonto, beschreibung=k.verwendungszweck[:200], status="vorschlag", konfidenz=0.3,
                extraktion_stufe="kontoauszug", klassifizierung_weg="-",
                hinweise_json=json.dumps(["Aus Kontobewegung angelegt – Beleg fehlt. USt-Satz ist eine Annahme."], ensure_ascii=False),
                extraktion_json=json.dumps({"kontobewegung_id": k.id, "verwendungszweck": k.verwendungszweck}, ensure_ascii=False))
    kat, weg, _ = klassifizierung.klassifiziere(
        s, {"lieferant": k.gegenkonto, "beschreibung": k.verwendungszweck, "richtung": richtung, "betrag_brutto": brutto}, cfg) \
        if (KI_AN["wert"] or regelwerk.passende_regel(s, k.gegenkonto, k.verwendungszweck)) else (None, "-", 0)
    if kat:
        b.kategorie_id, b.klassifizierung_weg = kat.id, weg
    s.add(b)
    s.commit()
    s.refresh(b)
    k.buchung_id = b.id
    s.add(k)
    s.commit()
    return b


@app.get("/ui/abgleich", response_class=HTMLResponse)
def ui_abgleich(jahr: Optional[int] = None, filter: str = "offen", s: Session = Depends(get_session)) -> HTMLResponse:
    jahr = jahr or _standardjahr(s)
    zeilen = matching.abgleich(s, jahr)
    regeln_ = s.exec(select(IgnorRegel).order_by(IgnorRegel.muster)).all()
    kats = _kats(s)
    vorschlag = {}
    for z in zeilen:
        if z["status"] == "kein_beleg":
            r = regelwerk.passende_regel(s, z["k"].gegenkonto, z["k"].verwendungszweck)
            vorschlag[z["k"].id] = kats.get(r.kategorie_id).name if r and r.kategorie_id in kats else ""
    return _html(ui.abgleich_view(zeilen, regeln_, jahr, filter, vorschlag))


@app.post("/api/abgleich/aktion", response_class=HTMLResponse)
async def api_abgleich_aktion(request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    """anlegen | ignorieren | regel | loesen | freigeben – für eine Auswahl von Kontobewegungen."""
    form = await request.form()
    aktion = form.get("aktion", "")
    ids = [int(x) for x in form.getlist("ids") if str(x).isdigit()]
    jahr = int(form["jahr"]) if str(form.get("jahr", "")).isdigit() else None
    n = 0
    for kid in ids:
        k = s.get(Kontobewegung, kid)
        if not k:
            continue
        if aktion == "anlegen" and not k.buchung_id and not k.ignoriert:
            _buchung_aus_konto(s, k); n += 1
        elif aktion == "ignorieren":
            k.ignoriert = True; s.add(k); n += 1
        elif aktion == "freigeben":
            k.ignoriert = False; s.add(k); n += 1
        elif aktion == "loesen":
            k.buchung_id = None; s.add(k); n += 1
        elif aktion == "regel":
            muster = (k.gegenkonto or k.verwendungszweck[:40]).strip().lower()
            if muster and not s.exec(select(IgnorRegel).where(IgnorRegel.muster == muster)).first():
                s.add(IgnorRegel(muster=muster))
            k.ignoriert = True; s.add(k); n += 1
    s.commit()
    if aktion == "regel":
        matching.ignorregeln_anwenden(s)
    text = {"anlegen": f"{n} Buchungsvorschläge angelegt – jetzt unter „Prüfen“.", "ignorieren": f"{n} ignoriert.",
            "freigeben": f"{n} wieder freigegeben.", "loesen": f"{n} Zuordnungen gelöst.", "regel": f"{n} ignoriert und als Regel gemerkt."}.get(aktion, "Nichts geändert.")
    return _html(ui.meldung_box(text) + ui_abgleich(jahr, "offen", s).body.decode())


@app.post("/api/abgleich/{konto_id}/zuordnen", response_class=HTMLResponse)
def api_abgleich_zuordnen(konto_id: int, buchung_id: int = Form(...), jahr: Optional[int] = Form(None), s: Session = Depends(get_session)) -> HTMLResponse:
    k = s.get(Kontobewegung, konto_id)
    if k and s.get(Buchung, buchung_id):
        k.buchung_id = buchung_id
        s.add(k)
        s.commit()
    return ui_abgleich(jahr, "offen", s)


@app.post("/api/abgleich/{konto_id}/beleg", response_class=HTMLResponse)
async def api_abgleich_beleg(konto_id: int, datei: UploadFile = File(...), jahr: Optional[int] = Form(None),
                             s: Session = Depends(get_session)) -> HTMLResponse:
    """Rechnung zu einer Kontobewegung hochladen: importieren und direkt zuordnen."""
    k = s.get(Kontobewegung, konto_id)
    if not k:
        raise HTTPException(404)
    daten = await datei.read()
    richtung = "einnahme" if k.betrag > 0 else "ausgabe"
    erg = pipeline.importiere_datei(s, daten, datei.filename or "beleg", herkunft=f"abgleich:{k.id}", ki_erlaubt=KI_AN["wert"], richtung=richtung)
    hinweis = ""
    if erg.buchung_id:
        b = s.get(Buchung, erg.buchung_id)
        if b and not k.buchung_id:
            k.buchung_id = b.id
            s.add(k)
            if abs(b.betrag_brutto - abs(k.betrag)) > 0.005:
                hinweis = f" Achtung: Rechnungsbetrag {export.eur_fmt(b.betrag_brutto)} weicht von der Kontobewegung {export.eur_fmt(abs(k.betrag))} ab – bitte unter „Prüfen“ kontrollieren."
            s.commit()
    meldung = f"{datei.filename}: {erg.status}, {erg.meldung}.{hinweis}"
    return _html(ui.meldung_box(meldung, "warn-box" if hinweis or erg.status != "neu" else "ok-box") + ui_abgleich(jahr or k.datum.year, "offen", s).body.decode())


@app.post("/api/ignorregel/neu", response_class=HTMLResponse)
def api_ignorregel_neu(muster: str = Form(...), jahr: Optional[int] = Form(None), s: Session = Depends(get_session)) -> HTMLResponse:
    m = muster.strip().lower()
    if m and not s.exec(select(IgnorRegel).where(IgnorRegel.muster == m)).first():
        s.add(IgnorRegel(muster=m))
        s.commit()
    n = matching.ignorregeln_anwenden(s)
    return _html(ui.meldung_box(f"Regel „{m}“ angelegt, {n} Kontobewegungen ignoriert.") + ui_abgleich(jahr, "offen", s).body.decode())


@app.post("/api/ignorregel/{regel_id}/loeschen", response_class=HTMLResponse)
def api_ignorregel_loeschen(regel_id: int, jahr: Optional[int] = Form(None), s: Session = Depends(get_session)) -> HTMLResponse:
    r = s.get(IgnorRegel, regel_id)
    if r:
        s.delete(r)
        s.commit()
    return ui_abgleich(jahr, "offen", s)


# -------------------------------------------------------- Offene Punkte

@app.get("/ui/offen", response_class=HTMLResponse)
def ui_offen(s: Session = Depends(get_session)) -> HTMLResponse:
    op = matching.offene_punkte(s)
    kandidaten = {k.id: matching.kandidaten_fuer(s, k) for k in op["ohne_beleg"][:100]}
    funde = s.exec(select(MailFund).where(MailFund.status == "offen").order_by(MailFund.datum.desc())).all()
    return _html(ui.offen_view(op, kandidaten, funde, _kats(s)))


def _protokoll(s: Session, aktion: str, details: str, buchung_id: Optional[int] = None) -> None:
    s.add(Protokoll(aktion=aktion, details=details, buchung_id=buchung_id))


@app.post("/api/ohnekonto/aktion", response_class=HTMLResponse)
async def api_ohnekonto_aktion(request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    """Beleg ohne Kontobewegung: privat | stornieren (Vorschläge werden gelöscht, Bestätigte storniert)."""
    form = await request.form()
    aktion = form.get("aktion", "")
    ids = [int(x) for x in form.getlist("ids") if str(x).isdigit()]
    n = 0
    for bid in ids:
        b = s.get(Buchung, bid)
        if not b:
            continue
        if aktion == "privat":
            b.privat_verauslagt = True
            s.add(b)
            _protokoll(s, "privat_verauslagt", f"{b.datum} {b.lieferant} {b.betrag_brutto:.2f}", b.id)
            n += 1
        elif aktion == "stornieren":
            if b.status == "bestaetigt":
                b.storniert = True
                s.add(b)
                _protokoll(s, "storniert", f"{b.datum} {b.lieferant} {b.betrag_brutto:.2f}", b.id)
            else:
                _protokoll(s, "geloescht", f"Vorschlag {b.datum} {b.lieferant} {b.betrag_brutto:.2f}", b.id)
                _buchung_loeschen(s, b)
            n += 1
    s.commit()
    text = {"privat": f"{n} als privat verauslagt markiert.", "stornieren": f"{n} storniert bzw. gelöscht."}.get(aktion, "Nichts geändert.")
    return _html(ui.meldung_box(text) + ui_offen(s).body.decode())


def _paare(form) -> list[tuple[int, int]]:
    out = []
    for p in form.getlist("paare"):
        try:
            a, b = (int(x) for x in str(p).split("-"))
            out.append((min(a, b), max(a, b)))
        except ValueError:
            continue
    return out


@app.post("/api/doppel/zusammenfuehren", response_class=HTMLResponse)
async def api_zusammenfuehren(request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    """Ältere Buchungs-ID bleibt, neuere geht; Beleg und Kontobewegung wandern mit; Protokoll."""
    form = await request.form()
    n = 0
    for alt_id, neu_id in _paare(form):
        alt, neu = s.get(Buchung, alt_id), s.get(Buchung, neu_id)
        if not alt or not neu:
            continue
        if not alt.beleg_id and neu.beleg_id:
            alt.beleg_id, neu.beleg_id = neu.beleg_id, None
        for k in s.exec(select(Kontobewegung).where(Kontobewegung.buchung_id == neu.id)).all():
            k.buchung_id = alt.id
            s.add(k)
        if alt.status != "bestaetigt" and neu.status == "bestaetigt":
            alt.status, alt.bestaetigt_am, alt.konfidenz = "bestaetigt", neu.bestaetigt_am, 1.0
            alt.kategorie_id, alt.eur_zeile = neu.kategorie_id, neu.eur_zeile
        s.add(alt)
        _protokoll(s, "zusammengefuehrt", f"#{neu.id} in #{alt.id} ({alt.datum} {alt.lieferant} {alt.betrag_brutto:.2f})", alt.id)
        _buchung_loeschen(s, neu)
        n += 1
    s.commit()
    return _html(ui.meldung_box(f"{n} Paare zusammengeführt.") + ui_offen(s).body.decode())


@app.post("/api/doppel/unterschiedlich", response_class=HTMLResponse)
async def api_unterschiedlich(request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    form = await request.form()
    n = 0
    for a, b in _paare(form):
        if not s.exec(select(DedupIgnoriert).where(DedupIgnoriert.a_id == a, DedupIgnoriert.b_id == b)).first():
            s.add(DedupIgnoriert(a_id=a, b_id=b))
            n += 1
    s.commit()
    return _html(ui.meldung_box(f"{n} Paare als geprüft markiert – tauchen nicht mehr auf.") + ui_offen(s).body.decode())


@app.post("/api/matching", response_class=HTMLResponse)
def api_matching(s: Session = Depends(get_session)) -> HTMLResponse:
    matching.matche(s)
    return ui_offen(s)


@app.post("/api/konto/{konto_id}/zuordnen", response_class=HTMLResponse)
def api_zuordnen(konto_id: int, buchung_id: int = Form(...), s: Session = Depends(get_session)) -> HTMLResponse:
    k = s.get(Kontobewegung, konto_id)
    if k and s.get(Buchung, buchung_id):
        k.buchung_id = buchung_id
        s.add(k)
        s.commit()
    return ui_offen(s)


@app.post("/api/konto/{konto_id}/ignorieren", response_class=HTMLResponse)
def api_ignorieren(konto_id: int, s: Session = Depends(get_session)) -> HTMLResponse:
    k = s.get(Kontobewegung, konto_id)
    if k:
        k.ignoriert = True
        s.add(k)
        s.commit()
    return ui_offen(s)


@app.post("/api/konto/{konto_id}/buchung-anlegen", response_class=HTMLResponse)
def api_konto_buchung(konto_id: int, s: Session = Depends(get_session)) -> HTMLResponse:
    """Buchung ohne Beleg aus einer Kontobewegung – bleibt Vorschlag, bis der Mensch bestätigt."""
    k = s.get(Kontobewegung, konto_id)
    if not k:
        raise HTTPException(404)
    b = _buchung_aus_konto(s, k)
    return _pruefen_detail(s, b)


@app.post("/api/mailfund/{fund_id}/{status}", response_class=HTMLResponse)
def api_mailfund(fund_id: int, status: str, s: Session = Depends(get_session)) -> HTMLResponse:
    m = s.get(MailFund, fund_id)
    if m and status in ("erledigt", "ignoriert", "offen"):
        m.status = status
        s.add(m)
        s.commit()
    return ui_offen(s)


# -------------------------------------------------------- Jahresabschluss

@app.get("/ui/jahresabschluss", response_class=HTMLResponse)
def ui_jahresabschluss(jahr: Optional[int] = None, s: Session = Depends(get_session)) -> HTMLResponse:
    jahr = jahr or date.today().year
    cfg = config.regeln()
    status = {f.frage_key: {"erledigt": f.erledigt, "notiz": f.notiz} for f in s.exec(select(Fragebogen).where(Fragebogen.jahr == jahr)).all()}
    kats = _kats(s)
    summen: dict[str, float] = {}
    for b in s.exec(select(Buchung).where(Buchung.status == "bestaetigt")).all():
        if b.datum.year == jahr and b.kategorie_id in kats:
            sk = kats[b.kategorie_id].schluessel
            summen[sk] = summen.get(sk, 0.0) + b.betrag_brutto
    return _html(ui.jahresabschluss_view(jahr, cfg["jahresabschluss_fragen"], status, list(kats.values()), summen, cfg))


@app.post("/api/fragebogen/{jahr}/{key}/toggle", response_class=HTMLResponse)
def api_fragebogen(jahr: int, key: str, s: Session = Depends(get_session)) -> HTMLResponse:
    f = s.exec(select(Fragebogen).where(Fragebogen.jahr == jahr, Fragebogen.frage_key == key)).first()
    if not f:
        f = Fragebogen(jahr=jahr, frage_key=key)
    f.erledigt = not f.erledigt
    s.add(f)
    s.commit()
    return ui_jahresabschluss(jahr, s)


# --------------------------------------------------------------- Export

@app.get("/ui/export", response_class=HTMLResponse)
def ui_export(jahr: Optional[int] = None, s: Session = Depends(get_session)) -> HTMLResponse:
    jahr = jahr or _standardjahr(s)
    cfg = config.regeln()
    buchungen = _aktive(s)
    eur = steuerlogik.eur_zeilen(buchungen, _kats(s), s.exec(select(Anlagegut)).all(), jahr, cfg)
    ustva = [steuerlogik.ustva(buchungen, jahr, q, cfg) for q in (1, 2, 3, 4)]
    return _html(ui.export_view(jahr, eur, ustva, _jahre(s)))


def _download(inhalt: bytes | str, name: str, typ: str) -> Response:
    daten = inhalt.encode("utf-8-sig") if isinstance(inhalt, str) else inhalt
    return Response(daten, media_type=typ, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/export/eur.csv")
def export_eur_csv(jahr: int, s: Session = Depends(get_session)):
    eur = steuerlogik.eur_zeilen(_aktive(s), _kats(s), s.exec(select(Anlagegut)).all(), jahr, config.regeln())
    return _download(export.eur_csv(eur), f"EUER_{jahr}.csv", "text/csv")


@app.get("/export/eur.json")
def export_eur_json(jahr: int, s: Session = Depends(get_session)):
    eur = steuerlogik.eur_zeilen(_aktive(s), _kats(s), s.exec(select(Anlagegut)).all(), jahr, config.regeln())
    return JSONResponse({"jahr": jahr, "zeilen": eur})


@app.get("/export/eur.pdf")
def export_eur_pdf(jahr: int, s: Session = Depends(get_session)):
    eur = steuerlogik.eur_zeilen(_aktive(s), _kats(s), s.exec(select(Anlagegut)).all(), jahr, config.regeln())
    return Response(export.eur_pdf(eur, jahr), media_type="application/pdf")


@app.get("/export/quartale.csv")
def export_quartale_csv(jahr: int, modus: str = "brutto", s: Session = Depends(get_session)):
    return _download(export.quartale_csv(_uebersicht(s, jahr), modus), f"Quartale_{jahr}_{modus}.csv", "text/csv")


@app.get("/export/quartale.pdf")
def export_quartale_pdf(jahr: int, modus: str = "brutto", s: Session = Depends(get_session)):
    return Response(export.quartale_pdf(_uebersicht(s, jahr), modus), media_type="application/pdf")


@app.get("/export/belegjournal.csv")
def export_journal(jahr: Optional[int] = None, s: Session = Depends(get_session)):
    buchungen = [b for b in s.exec(select(Buchung)).all() if jahr is None or b.datum.year == jahr]
    belege = {b.id: b for b in s.exec(select(Beleg)).all()}
    protokoll = s.exec(select(Protokoll).order_by(Protokoll.zeitpunkt)).all()
    return _download(export.belegjournal_csv(buchungen, belege, _kats(s), protokoll), f"Belegjournal_{jahr or 'alle'}.csv", "text/csv")


@app.get("/export/ustva/{jahr}/{q}")
def export_ustva(jahr: int, q: int, s: Session = Depends(get_session)):
    u = steuerlogik.ustva(_aktive(s), jahr, q, config.regeln())
    return JSONResponse({"jahr": jahr, "quartal": q, "kennzahlen": u["kennzahlen"], "zahllast": u["zahllast"],
                         "positionen": [{"buchung_id": p["buchung"].id, "lieferant": p["buchung"].lieferant, "netto": p["buchung"].betrag_netto,
                                         "kz_basis": p["kz_basis"], "kz_steuer": p["kz_steuer"], "steuer": p["steuer"]} for p in u["positionen"]]})


# --------------------------------------------------------- Einstellungen

def _einstellungen(s: Session, meldung: str = "", typ: str = "ok-box") -> HTMLResponse:
    cfg = config.regeln()
    e = mail.einstellungen()
    regeln_ = s.exec(select(Regel).order_by(Regel.prioritaet, Regel.muster)).all()
    pfade = {"db": str(config.db_path()), "belege": str(config.beleg_dir()), "regeln": str(config.regeln_path()),
             "vision": cfg["ollama"]["vision_modell"], "text": cfg["ollama"]["text_modell"], "version": config.version()}
    hat_pw = bool(e["imap"].get("user") and mail.passwort_lesen(e["imap"]["user"]))
    return _html(ui.einstellungen_view(ollama.verfuegbar(cfg), e, hat_pw, regeln_, _kats(s), pfade, meldung, typ))


@app.get("/ui/einstellungen", response_class=HTMLResponse)
def ui_einstellungen(s: Session = Depends(get_session)) -> HTMLResponse:
    return _einstellungen(s)


@app.post("/api/config/reload", response_class=HTMLResponse)
def api_config_reload(s: Session = Depends(get_session)) -> HTMLResponse:
    config.regeln_neu_laden()
    kategorien_synchronisieren(s)
    return _einstellungen(s, "steuerregeln.json neu geladen, Kategorien synchronisiert.")


@app.post("/api/mail/einstellungen", response_class=HTMLResponse)
def api_mail_einstellungen(imap_host: str = Form(""), imap_user: str = Form(""), imap_ordner: str = Form("Belege"),
                           imap_passwort: str = Form(""), emlx_pfad: str = Form(""), emlx_filter: str = Form(""),
                           s: Session = Depends(get_session)) -> HTMLResponse:
    e = mail.einstellungen()
    e["imap"].update({"host": imap_host.strip(), "user": imap_user.strip(), "ordner": imap_ordner.strip() or "Belege", "aktiv": bool(imap_host.strip())})
    e["emlx"].update({"pfad": emlx_pfad.strip(), "ordner_filter": emlx_filter.strip(), "aktiv": bool(emlx_pfad.strip())})
    mail.einstellungen_speichern(e)
    meldung, typ = "Einstellungen gespeichert.", "ok-box"
    if imap_passwort:
        if mail.passwort_setzen(imap_user.strip(), imap_passwort):
            meldung += " Passwort im Schlüsselbund abgelegt."
        else:
            meldung, typ = "Einstellungen gespeichert, aber das Passwort konnte NICHT im Schlüsselbund abgelegt werden (keyring fehlt?). Es wurde nirgends gespeichert.", "fehler-box"
    return _einstellungen(s, meldung, typ)


@app.post("/api/mail/imap", response_class=HTMLResponse)
def api_mail_imap(s: Session = Depends(get_session)) -> HTMLResponse:
    erg = mail.imap_lauf(s, KI_AN["wert"])
    if erg.get("fehler"):
        return _einstellungen(s, erg["fehler"], "fehler-box")
    return _einstellungen(s, f"IMAP: {erg['neue_mails']} neue Mails, {erg['importiert']} Anhänge importiert, "
                          f"{erg['duplikate']} Duplikate, {erg['links']} Link-Mails → „manuell holen“, {erg['ignoriert']} ignoriert.")


@app.post("/api/mail/emlx", response_class=HTMLResponse)
def api_mail_emlx(s: Session = Depends(get_session)) -> HTMLResponse:
    erg = mail.emlx_lauf(s, KI_AN["wert"])
    if erg.get("fehler"):
        return _einstellungen(s, erg["fehler"], "fehler-box")
    return _einstellungen(s, f"Apple Mail: {erg['neue_mails']} neue Mails, {erg['importiert']} Anhänge importiert, "
                          f"{erg['duplikate']} Duplikate, {erg['links']} Link-Mails → „manuell holen“, {erg['ignoriert']} ignoriert.")


@app.post("/api/regel/neu", response_class=HTMLResponse)
def api_regel_neu(muster: str = Form(...), kategorie_id: int = Form(...), ist_regex: str = Form(""), s: Session = Depends(get_session)) -> HTMLResponse:
    s.add(Regel(muster=muster.strip().lower() if not ist_regex else muster.strip(), kategorie_id=kategorie_id, ist_regex=ist_regex == "1", prioritaet=10))
    s.commit()
    return _einstellungen(s, "Regel angelegt.")


@app.post("/api/regel/{regel_id}/loeschen", response_class=HTMLResponse)
def api_regel_loeschen(regel_id: int, s: Session = Depends(get_session)) -> HTMLResponse:
    r = s.get(Regel, regel_id)
    if r:
        s.delete(r)
        s.commit()
    return _einstellungen(s, "Regel gelöscht.")


@app.post("/api/beenden", response_class=HTMLResponse)
def api_beenden() -> HTMLResponse:
    """Server sauber beenden (für den Dock-Start ohne Terminal)."""
    import os, threading
    threading.Timer(0.6, lambda: os._exit(0)).start()
    return _html('<section><h2>Steuerfuchs ist beendet.</h2><p class="muted">Du kannst dieses Fenster schließen. Zum Neustart die App im Dock anklicken.</p></section>')


@app.get("/gesund", response_class=PlainTextResponse)
def gesund() -> str:
    return "ok"
