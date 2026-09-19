"""Cash Angel – Haushaltsanalyse aus Kontoauszügen. FastAPI + HTMX, alles lokal."""
from __future__ import annotations

import json
import os
import signal
import threading
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlmodel import Session, select

from . import analyse, config, ui
from .db import engine, init_db, kategorien_synchronisieren
from .kontoauszug import lese_kontoauszug
from .models import AboStatus, Bewegung, Geloescht, Kategorie, Regel

app = FastAPI(title="Cash Angel")
init_db()


def get_session():
    with Session(engine()) as s:
        yield s


def _html(inhalt: str) -> HTMLResponse:
    return HTMLResponse(inhalt)


def _kats(s: Session) -> dict[int, Kategorie]:
    return {k.id: k for k in s.exec(select(Kategorie).where(Kategorie.aktiv == True)).all()}  # noqa: E712


def _kats_nach_schluessel(s: Session) -> dict[str, Kategorie]:
    return {k.schluessel: k for k in _kats(s).values()}


def _alle(s: Session) -> list[Bewegung]:
    return s.exec(select(Bewegung).order_by(Bewegung.datum.desc(), Bewegung.id.desc())).all()


def _letztes_datum(s: Session) -> date:
    b = s.exec(select(Bewegung).order_by(Bewegung.datum.desc())).first()
    return b.datum if b else date.today()


def _zeitraum(s: Session, zeitraum: Optional[str]) -> str:
    return zeitraum or "12m"


def _monate(s: Session, zeitraum: str) -> list[str]:
    return analyse.monate_im_zeitraum(zeitraum, _letztes_datum(s))


def _zeitraeume(s: Session) -> list[dict]:
    """Auswahl für den Kopf: relative Zeiträume, Jahre und einzelne Monate mit Daten."""
    daten = s.exec(select(Bewegung.datum)).all()
    monate = sorted({analyse.monat_key(d) for d in daten}, reverse=True)
    jahre = sorted({m[:4] for m in monate}, reverse=True)
    out = [{"wert": "3m", "name": "letzte 3 Monate"}, {"wert": "6m", "name": "letzte 6 Monate"}, {"wert": "12m", "name": "letzte 12 Monate"}]
    out += [{"wert": f"jahr:{j}", "name": f"Jahr {j}"} for j in jahre]
    out += [{"wert": f"monat:{m}", "name": analyse.monat_name(m)} for m in monate[:36]]
    return out


def _klassifiziere_neu(s: Session, nur_offene: bool = True) -> int:
    kats = _kats_nach_schluessel(s)
    regeln = s.exec(select(Regel)).all()
    cfg = config.konfig()
    n = 0
    for b in s.exec(select(Bewegung)).all():
        if nur_offene and b.weg == "manuell":
            continue
        k, person, weg = analyse.klassifiziere(b, kats, regeln, cfg)
        neu_id = k.id if k else None
        if neu_id != b.kategorie_id or person != b.person or weg != b.weg:
            b.kategorie_id, b.person, b.weg = neu_id, person, weg
            s.add(b)
            n += 1
    s.commit()
    return n


# ---------------------------------------------------------------- Seiten

@app.get("/", response_class=HTMLResponse)
def start() -> HTMLResponse:
    html = (config.STATIC / "index.html").read_text(encoding="utf-8").replace("__VERSION__", config.version())
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/static/{name}")
def static(name: str):
    p = config.STATIC / name
    if not p.exists() or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


@app.get("/gesund")
def gesund() -> dict:
    return {"ok": True}


@app.get("/api/version")
def api_version() -> dict:
    return {"version": config.version(), "app": "Cash Angel"}


@app.post("/api/beenden")
def api_beenden() -> dict:
    threading.Timer(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
    return {"ok": True}


@app.get("/api/status")
def api_status(zeitraum: Optional[str] = None, s: Session = Depends(get_session)) -> dict:
    kats = _kats_nach_schluessel(s)
    sonst = {kats["sonstiges"].id if "sonstiges" in kats else -1, kats["sonstige_einnahmen"].id if "sonstige_einnahmen" in kats else -1}
    offen = sum(1 for b in s.exec(select(Bewegung)).all() if b.kategorie_id in sonst and not b.ignoriert)
    return {"zeitraeume": _zeitraeume(s), "standard": "12m", "bewegungen": len(s.exec(select(Bewegung)).all()), "offen": offen,
            "personen": config.konfig().get("personen", [])}


@app.get("/ui/uebersicht", response_class=HTMLResponse)
def ui_uebersicht(zeitraum: Optional[str] = None, s: Session = Depends(get_session)) -> HTMLResponse:
    z = _zeitraum(s, zeitraum)
    if not s.exec(select(Bewegung)).first():
        return _html(ui.leer_view())
    return _html(ui.uebersicht_view(z, analyse.zeitraum_beschriftung(z)))


@app.get("/api/uebersicht")
def api_uebersicht(zeitraum: Optional[str] = None, s: Session = Depends(get_session)) -> dict:
    z = _zeitraum(s, zeitraum)
    monate = _monate(s, z)
    kats = _kats(s)
    alle = _alle(s)
    bilanz = analyse.monatsbilanz(alle, kats, monate)
    abos = analyse.abos_finden(alle, kats, _letztes_datum(s))
    status = {a.partner: a.status for a in s.exec(select(AboStatus)).all()}
    abos = [a for a in abos if status.get(a["partner"], "ok") == "ok"]
    ks = {k.schluessel: k for k in kats.values()}
    kategorien = [{"schluessel": sk, "name": ks[sk].name if sk in ks else sk, "farbe": ks[sk].farbe if sk in ks else "#64748b", "wert": v,
                   "fix": ks[sk].fix if sk in ks else False} for sk, v in bilanz["kategorien"].items()]
    return {"zeitraum": z, "beschriftung": analyse.zeitraum_beschriftung(z), "monate": bilanz["monate"], "summe": bilanz["summe"], "schnitt": bilanz["schnitt"],
            "monate_mit_daten": bilanz["monate_mit_daten"], "kategorien": kategorien,
            "einnahmequellen": [{"name": k, "wert": v} for k, v in bilanz["einnahmequellen"].items()],
            "abos": {"anzahl": sum(1 for a in abos if a["aktiv"]), "monatlich": round(sum(a["monatlich"] for a in abos if a["aktiv"]), 2)}}


@app.get("/ui/abos", response_class=HTMLResponse)
def ui_abos(zeitraum: Optional[str] = None, s: Session = Depends(get_session)) -> HTMLResponse:
    kats = _kats(s)
    alle = _alle(s)
    abos = analyse.abos_finden(alle, kats, _letztes_datum(s))
    status = {a.partner: a for a in s.exec(select(AboStatus)).all()}
    bilanz = analyse.monatsbilanz(alle, kats, _monate(s, _zeitraum(s, zeitraum)))
    return _html(ui.abos_view(abos, status, bilanz["schnitt"].get("ausgaben", 0.0), bilanz["schnitt"].get("einnahmen", 0.0)))


@app.post("/api/abo/status", response_class=HTMLResponse)
def api_abo_status(partner: str = Form(...), status: str = Form("ok"), s: Session = Depends(get_session)) -> HTMLResponse:
    a = s.exec(select(AboStatus).where(AboStatus.partner == partner)).first() or AboStatus(partner=partner)
    a.status = status if status in ("ok", "gekuendigt", "kein_abo") else "ok"
    s.add(a)
    s.commit()
    return ui_abos(None, s)


@app.get("/ui/buchungen", response_class=HTMLResponse)
def ui_buchungen(zeitraum: Optional[str] = None, kategorie: str = "", q: str = "", konto: str = "", nur_offen: str = "",
                 s: Session = Depends(get_session)) -> HTMLResponse:
    z = _zeitraum(s, zeitraum)
    monate = set(_monate(s, z))
    kats = _kats(s)
    ks = {k.schluessel: k for k in kats.values()}
    ql = q.strip().lower()
    zeilen = []
    for b in _alle(s):
        if analyse.monat_key(b.datum) not in monate:
            continue
        if kategorie and (kats.get(b.kategorie_id or -1) is None or kats[b.kategorie_id].schluessel != kategorie):
            continue
        if konto and b.konto != konto:
            continue
        if nur_offen and not (b.kategorie_id in (ks.get("sonstiges").id if "sonstiges" in ks else -1, ks.get("sonstige_einnahmen").id if "sonstige_einnahmen" in ks else -1)):
            continue
        if ql and ql not in f"{b.gegenkonto} {b.verwendungszweck} {b.betrag:.2f} {b.konto}".lower().replace(".", ","):
            continue
        zeilen.append(b)
    konten = sorted({b.konto for b in s.exec(select(Bewegung)).all() if b.konto})
    return _html(ui.buchungen_view(zeilen, kats, config.konfig().get("personen", []), z, kategorie, q, konto, konten, bool(nur_offen)))


@app.post("/api/bewegung/{bid}/kategorie", response_class=HTMLResponse)
def api_bewegung_kategorie(bid: int, kategorie_id: str = Form(""), person: str = Form(""), lernen: str = Form("1"),
                           s: Session = Depends(get_session)) -> HTMLResponse:
    """Kategorie einer Zeile setzen; standardmäßig wird die Zuordnung Partner → Kategorie gelernt und auf gleiche Partner angewandt."""
    b = s.get(Bewegung, bid)
    if not b:
        raise HTTPException(404)
    kats = _kats(s)
    if kategorie_id.isdigit() and int(kategorie_id) in kats:
        b.kategorie_id = int(kategorie_id)
    b.person = person.strip()
    b.weg = "manuell"
    s.add(b)
    n = 0
    if lernen == "1" and b.partner and b.kategorie_id:
        n = _regel_anwenden(s, b, auch_manuelle=False)
    s.commit()
    s.refresh(b)
    return _html(ui.buchung_zeile(b, kats, config.konfig().get("personen", []), gespeichert=True, hinweis=(f"+{n} gleiche" if n else "")))


def _seite(b: Bewegung) -> str:
    return "einnahme" if b.betrag > 0 else "ausgabe"


def _regel_anwenden(s: Session, b: Bewegung, auch_manuelle: bool) -> int:
    """Zuordnung Partner → Kategorie merken (getrennt nach Einnahme/Ausgabe) und auf gleiche Buchungen derselben Seite anwenden."""
    seite = _seite(b)
    r = s.exec(select(Regel).where(Regel.muster == b.partner, Regel.art == seite)).first()
    if r is None:
        alt = s.exec(select(Regel).where(Regel.muster == b.partner, Regel.art == "")).first()
        r = alt or Regel(muster=b.partner, kategorie_id=b.kategorie_id, art=seite)
    r.kategorie_id, r.person, r.art = b.kategorie_id, b.person, seite
    s.add(r)
    s.commit()
    s.refresh(r)
    n = 0
    gesamt = 1
    for o in s.exec(select(Bewegung).where(Bewegung.partner == b.partner, Bewegung.id != b.id)).all():
        if _seite(o) != seite:
            continue
        gesamt += 1
        if (o.weg != "manuell" or auch_manuelle) and (o.kategorie_id != b.kategorie_id or o.person != b.person):
            o.kategorie_id, o.person, o.weg = b.kategorie_id, b.person, f"regel:{r.id}"
            s.add(o)
            n += 1
    s.commit()
    return n if not auch_manuelle else (n, gesamt)


@app.post("/api/bewegung/{bid}/kategorie/alle", response_class=HTMLResponse)
def api_bewegung_kategorie_alle(bid: int, kategorie_id: str = Form(""), person: str = Form(""), zeitraum: Optional[str] = Form(None), kategorie: str = Form(""),
                                q: str = Form(""), konto: str = Form(""), nur_offen: str = Form(""), s: Session = Depends(get_session)) -> HTMLResponse:
    """„Auf alle anwenden“: Kategorie dieser Zeile allen Buchungen desselben Empfängers auf derselben Seite (Einnahme oder Ausgabe) geben,
    auch von Hand gesetzten. Liefert die Liste mit den aktuellen Filtern zurück."""
    b = s.get(Bewegung, bid)
    if not b:
        raise HTTPException(404)
    kats = _kats(s)
    if kategorie_id.isdigit() and int(kategorie_id) in kats:
        b.kategorie_id = int(kategorie_id)
    b.person = person.strip()
    b.weg = "manuell"
    s.add(b)
    s.commit()
    n, gesamt = _regel_anwenden(s, b, auch_manuelle=True) if b.partner and b.kategorie_id else (0, 1)
    k = kats.get(b.kategorie_id or -1)
    seite = "Einnahmen" if b.betrag > 0 else "Ausgaben"
    antwort = ui_buchungen(zeitraum, kategorie, q, konto, nur_offen, s)
    text = f"„{k.name if k else '?'}“ gilt jetzt für alle {gesamt} {seite} von {b.gegenkonto or b.partner}" + (f", {n} davon geändert." if n else " – die hatten sie schon alle.")
    return _html(ui.meldung_box(text) + antwort.body.decode("utf-8"))


@app.post("/api/bewegungen/aktion", response_class=HTMLResponse)
async def api_bewegungen_aktion(request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    """Sammelaktionen aus der Buchungsliste: kategorie | ignorieren | freigeben | loeschen."""
    form = await request.form()
    aktion = str(form.get("aktion", ""))
    ids = [int(t) for x in form.getlist("ids") for t in str(x).split(",") if t.strip().isdigit()]
    kats = _kats(s)
    n = 0
    for bid in ids:
        b = s.get(Bewegung, bid)
        if not b:
            continue
        if aktion == "kategorie" and str(form.get("kategorie_id", "")).isdigit() and int(form["kategorie_id"]) in kats:
            b.kategorie_id, b.weg = int(form["kategorie_id"]), "manuell"
            s.add(b); n += 1
        elif aktion == "ignorieren":
            b.ignoriert = True; s.add(b); n += 1
        elif aktion == "freigeben":
            b.ignoriert = False; s.add(b); n += 1
        elif aktion == "loeschen":
            if b.fingerprint and not s.exec(select(Geloescht).where(Geloescht.fingerprint == b.fingerprint)).first():
                s.add(Geloescht(fingerprint=b.fingerprint))
            s.delete(b); n += 1
    s.commit()
    text = {"kategorie": f"{n} Buchungen umkategorisiert.", "ignorieren": f"{n} ausgeblendet (zählen nicht mehr).", "freigeben": f"{n} wieder eingeblendet.",
            "loeschen": f"{n} gelöscht – ein erneuter Import bringt sie nicht zurück."}.get(aktion, "Nichts geändert.")
    antwort = ui_buchungen(str(form.get("zeitraum", "")) or None, str(form.get("kategorie", "")), str(form.get("q", "")), str(form.get("konto", "")), str(form.get("nur_offen", "")), s)
    return _html(ui.meldung_box(text) + antwort.body.decode())


@app.get("/ui/dubletten", response_class=HTMLResponse)
def ui_dubletten(s: Session = Depends(get_session)) -> HTMLResponse:
    return _dubletten(s)


def _dubletten(s: Session, meldung: str = "") -> HTMLResponse:
    gruppen = analyse.dubletten(s.exec(select(Bewegung)).all())
    return _html((ui.meldung_box(meldung) if meldung else "") + ui.dubletten_view(gruppen, _kats(s)))


@app.post("/api/dubletten/loeschen", response_class=HTMLResponse)
async def api_dubletten_loeschen(request: Request, s: Session = Depends(get_session)) -> HTMLResponse:
    """Ausgewählte Dubletten löschen – oder automatisch je Gruppe alle bis auf die zuerst importierte."""
    form = await request.form()
    if str(form.get("automatisch", "")):
        ids = [b.id for g in analyse.dubletten(s.exec(select(Bewegung)).all()) for b in g[1:]]
    else:
        ids = [int(t) for x in form.getlist("ids") for t in str(x).split(",") if t.strip().isdigit()]
    n = 0
    for bid in ids:
        b = s.get(Bewegung, bid)
        if not b:
            continue
        if b.fingerprint and not s.exec(select(Geloescht).where(Geloescht.fingerprint == b.fingerprint)).first():
            s.add(Geloescht(fingerprint=b.fingerprint))
        s.delete(b)
        n += 1
    s.commit()
    return _dubletten(s, f"{n} doppelte Buchungen gelöscht – ein erneuter Import bringt sie nicht zurück." if n else "Nichts gelöscht.")


@app.post("/api/daten/loeschen", response_class=HTMLResponse)
def api_daten_loeschen(zuordnungen: str = Form(""), merkliste: str = Form(""), s: Session = Depends(get_session)) -> HTMLResponse:
    """Alle Buchungen löschen; auf Wunsch auch gelernte Zuordnungen, Abo-Status und die Merkliste gelöschter Buchungen.
    Kategorien und Einstellungen (kategorien.json) bleiben."""
    n = 0
    for b in s.exec(select(Bewegung)).all():
        s.delete(b)
        n += 1
    teile = [f"{n} Buchungen gelöscht"]
    if zuordnungen:
        r = sum(1 for x in s.exec(select(Regel)).all() if not s.delete(x))
        a = sum(1 for x in s.exec(select(AboStatus)).all() if not s.delete(x))
        teile.append(f"{r} Zuordnungen und {a} Abo-Markierungen entfernt")
    if merkliste:
        g = sum(1 for x in s.exec(select(Geloescht)).all() if not s.delete(x))
        teile.append(f"Merkliste mit {g} gelöschten Buchungen geleert")
    s.commit()
    return _einstellungen(s, ", ".join(teile) + ". Kategorien und Einstellungen sind noch da.")


@app.get("/ui/import", response_class=HTMLResponse)
def ui_import(s: Session = Depends(get_session)) -> HTMLResponse:
    konten = sorted({b.konto for b in s.exec(select(Bewegung)).all() if b.konto})
    dateien: dict[str, int] = {}
    for b in s.exec(select(Bewegung)).all():
        dateien[b.quelle_datei] = dateien.get(b.quelle_datei, 0) + 1
    return _html(ui.import_view(konten, sorted(dateien.items(), key=lambda kv: kv[0], reverse=True)[:30]))


@app.post("/api/import", response_class=HTMLResponse)
async def api_import(datei: list[UploadFile] = File(...), konto: str = Form(""), s: Session = Depends(get_session)) -> HTMLResponse:
    kats = _kats_nach_schluessel(s)
    regeln = s.exec(select(Regel)).all()
    cfg = config.konfig()
    tomb = {g.fingerprint for g in s.exec(select(Geloescht)).all()}
    vorhanden = {b.fingerprint for b in s.exec(select(Bewegung)).all()}
    neu = dup = 0
    fehler = []
    for up in datei:
        daten = await up.read()
        try:
            bewegungen = lese_kontoauszug(daten, up.filename or "")
        except Exception as e:  # noqa: BLE001
            fehler.append(f"{up.filename}: {e}")
            continue
        if not bewegungen:
            fehler.append(f"{up.filename}: keine Buchungen erkannt (Format?)")
            continue
        for bw in bewegungen:
            fp = bw.fingerprint()
            if fp in vorhanden or fp in tomb:
                dup += 1
                continue
            vorhanden.add(fp)
            b = Bewegung(datum=bw.datum, betrag=bw.betrag, verwendungszweck=bw.verwendungszweck[:300], gegenkonto=bw.gegenkonto[:120],
                         gegen_iban=bw.gegen_iban, konto=konto.strip()[:60], quelle_datei=(up.filename or "")[:120], fingerprint=fp,
                         partner=analyse.partner_schluessel(bw.gegenkonto, bw.verwendungszweck))
            k, person, weg = analyse.klassifiziere(b, kats, regeln, cfg)
            b.kategorie_id, b.person, b.weg = (k.id if k else None), person, weg
            s.add(b)
            neu += 1
    s.commit()
    text = f"{neu} neue Buchungen eingelesen, {dup} waren schon bekannt."
    if fehler:
        text += " Probleme: " + "; ".join(fehler)
    antwort = ui_import(s)
    return _html(ui.meldung_box(text, "warn-box" if fehler or not neu else "ok-box") + antwort.body.decode())


@app.get("/ui/muster", response_class=HTMLResponse)
def ui_muster(zeitraum: Optional[str] = None, s: Session = Depends(get_session)) -> HTMLResponse:
    z = _zeitraum(s, zeitraum)
    if not s.exec(select(Bewegung)).first():
        return _html(ui.leer_view())
    kats = _kats(s)
    alle = _alle(s)
    abos = analyse.abos_finden(alle, kats, _letztes_datum(s))
    status = {a.partner: a.status for a in s.exec(select(AboStatus)).all()}
    abos = [a for a in abos if status.get(a["partner"], "ok") == "ok"]
    ins = analyse.insights(alle, kats, _monate(s, z), abos, config.konfig())
    return _html(ui.muster_view(ins, z, analyse.zeitraum_beschriftung(z)))


@app.get("/api/muster")
def api_muster(zeitraum: Optional[str] = None, s: Session = Depends(get_session)) -> dict:
    z = _zeitraum(s, zeitraum)
    kats = _kats(s)
    alle = _alle(s)
    abos = analyse.abos_finden(alle, kats, _letztes_datum(s))
    ins = analyse.insights(alle, kats, _monate(s, z), abos, config.konfig())
    ins.pop("karten", None)
    return ins


@app.get("/ui/einstellungen", response_class=HTMLResponse)
def ui_einstellungen(s: Session = Depends(get_session)) -> HTMLResponse:
    return _einstellungen(s)


def _einstellungen(s: Session, meldung: str = "") -> HTMLResponse:
    cfg = config.konfig()
    regeln = s.exec(select(Regel).order_by(Regel.muster)).all()
    return _html((ui.meldung_box(meldung) if meldung else "") + ui.einstellungen_view(cfg, list(_kats(s).values()), regeln, str(config.db_path()), config.version(), config.standard_schluessel()))


@app.post("/api/einstellungen", response_class=HTMLResponse)
def api_einstellungen(personen: str = Form(""), eigene_ibans: str = Form(""), kleinbetrag_grenze: str = Form("15"),
                      s: Session = Depends(get_session)) -> HTMLResponse:
    p = [x.strip() for x in personen.replace("\n", ",").split(",") if x.strip()]
    ib = [x.strip().replace(" ", "").upper() for x in eigene_ibans.replace("\n", ",").split(",") if x.strip()]
    try:
        grenze = float(kleinbetrag_grenze.replace(",", "."))
    except ValueError:
        grenze = 15.0
    config.konfig_setzen(personen=p, eigene_ibans=ib, kleinbetrag_grenze=grenze)
    kategorien_synchronisieren(s)
    n = _klassifiziere_neu(s)
    return _einstellungen(s, f"Gespeichert. {n} Buchungen neu zugeordnet.")


@app.post("/api/regel/{rid}/loeschen", response_class=HTMLResponse)
def api_regel_loeschen(rid: int, s: Session = Depends(get_session)) -> HTMLResponse:
    r = s.get(Regel, rid)
    if r:
        s.delete(r)
        s.commit()
    n = _klassifiziere_neu(s)
    return _einstellungen(s, f"Zuordnung gelöscht, {n} Buchungen neu zugeordnet.")


@app.post("/api/regel/{rid}", response_class=HTMLResponse)
def api_regel_aendern(rid: int, kategorie_id: str = Form(""), person: str = Form(""), s: Session = Depends(get_session)) -> HTMLResponse:
    """Gelernte Zuordnung neu vergeben: Kategorie (und Person) ändern, betroffene Buchungen ziehen nach."""
    r = s.get(Regel, rid)
    if not r:
        raise HTTPException(404)
    kats = _kats(s)
    if kategorie_id.isdigit() and int(kategorie_id) in kats:
        r.kategorie_id = int(kategorie_id)
        r.art = kats[r.kategorie_id].art if kats[r.kategorie_id].art in ("einnahme", "ausgabe") else r.art
    r.person = person.strip()
    s.add(r)
    s.commit()
    n = 0
    for o in s.exec(select(Bewegung).where(Bewegung.partner == r.muster)).all():
        if r.art and _seite(o) != r.art:
            continue
        if o.kategorie_id != r.kategorie_id or o.person != r.person:
            o.kategorie_id, o.person, o.weg = r.kategorie_id, r.person, f"regel:{r.id}"
            s.add(o)
            n += 1
    s.commit()
    n += _klassifiziere_neu(s)
    return _einstellungen(s, f"Zuordnung geändert, {n} Buchungen angepasst.")


@app.post("/api/kategorie/neu", response_class=HTMLResponse)
def api_kategorie_neu(name: str = Form(""), art: str = Form("ausgabe"), fix: str = Form(""), farbe: str = Form("#38bdf8"), muster: str = Form(""),
                      s: Session = Depends(get_session)) -> HTMLResponse:
    if not name.strip():
        return _einstellungen(s, "Bitte einen Namen für die Kategorie angeben.")
    schl = config.kategorie_anlegen(name, art, bool(fix), farbe, muster.replace("\n", ",").split(","))
    kategorien_synchronisieren(s)
    n = _klassifiziere_neu(s)
    return _einstellungen(s, f"Kategorie „{name.strip()}“ angelegt ({schl}). {n} Buchungen neu zugeordnet.")


@app.post("/api/kategorie/{schluessel}/loeschen", response_class=HTMLResponse)
def api_kategorie_loeschen(schluessel: str, s: Session = Depends(get_session)) -> HTMLResponse:
    k = s.exec(select(Kategorie).where(Kategorie.schluessel == schluessel)).first()
    if not k or not config.kategorie_entfernen(schluessel):
        return _einstellungen(s, "Standardkategorien lassen sich nicht entfernen.")
    ks = _kats_nach_schluessel(s)
    ersatz = ks.get("sonstige_einnahmen" if k.art == "einnahme" else "sonstiges")
    n = 0
    for o in s.exec(select(Bewegung).where(Bewegung.kategorie_id == k.id)).all():
        o.kategorie_id, o.weg = (ersatz.id if ersatz else None), "-"
        s.add(o)
        n += 1
    for r in s.exec(select(Regel).where(Regel.kategorie_id == k.id)).all():
        s.delete(r)
    s.delete(k)
    s.commit()
    n2 = _klassifiziere_neu(s)
    return _einstellungen(s, f"Kategorie „{k.name}“ entfernt; {n} Buchungen umgehängt, {n2} neu zugeordnet.")


@app.post("/api/neu-klassifizieren", response_class=HTMLResponse)
def api_neu_klassifizieren(alle: str = Form(""), s: Session = Depends(get_session)) -> HTMLResponse:
    n = _klassifiziere_neu(s, nur_offene=not alle)
    return _einstellungen(s, f"{n} Buchungen neu zugeordnet.")


@app.get("/api/export/buchungen.csv")
def export_csv(zeitraum: Optional[str] = None, s: Session = Depends(get_session)):
    import csv
    import io
    z = _zeitraum(s, zeitraum)
    monate = set(_monate(s, z))
    kats = _kats(s)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Datum", "Betrag", "Kategorie", "Person", "Partner", "Verwendungszweck", "Konto", "Ausgeblendet"])
    for b in _alle(s):
        if analyse.monat_key(b.datum) in monate:
            k = kats.get(b.kategorie_id or -1)
            w.writerow([b.datum.strftime("%d.%m.%Y"), f"{b.betrag:.2f}".replace(".", ","), k.name if k else "", b.person, b.gegenkonto, b.verwendungszweck, b.konto, "ja" if b.ignoriert else ""])
    return HTMLResponse(buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="cashangel-{z.replace(":", "-")}.csv"'})
