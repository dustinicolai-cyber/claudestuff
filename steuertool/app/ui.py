"""HTML-Fragmente für HTMX. Reine Funktionen: Daten rein, HTML raus.
Kein Template-System, damit das Tool in zwei Jahren noch ohne Abhängigkeitspflege startet.
"""
from __future__ import annotations

import json
from datetime import date
from html import escape as h

from .export import eur_fmt
from .models import Anlagegut, Beleg, Buchung, Kategorie, Kontobewegung, MailFund, Regel
from .steuerlogik import Bewertung, Zelle, afa_fuer_jahr

STUFEN = {"zugferd": "E-Rechnung (XML)", "pdf": "PDF-Text", "ocr": "Vision-OCR", "manuell": "manuell", "keine": "keine", "kontoauszug": "Kontoauszug"}


def d(x: date | None) -> str:
    return x.strftime("%d.%m.%Y") if x else ""


def konf_badge(k: float) -> str:
    cls = "ok" if k >= 0.8 else ("mid" if k >= 0.5 else "low")
    return f'<span class="badge {cls}" title="Konfidenz">{int(round(k * 100))} %</span>'


def stufe_badge(s: str) -> str:
    return f'<span class="badge stufe">{h(STUFEN.get(s, s))}</span>'


def hinweise_html(b: Buchung, bw: Bewertung | None = None) -> str:
    try:
        liste = json.loads(b.hinweise_json or "[]")
    except json.JSONDecodeError:
        liste = []
    out = "".join(f'<li>{h(x)}</li>' for x in liste)
    if bw:
        out += "".join(f'<li>{h(x)}</li>' for x in bw.hinweise)
        out += "".join(f'<li class="warn">⚠ {h(x)}</li>' for x in bw.warnungen)
    return f'<ul class="hinweise">{out}</ul>' if out else ""


# ------------------------------------------------------------- Import

def import_view(ollama_status: dict, ki_an: bool) -> str:
    ki = ("<span class='badge ok'>Ollama erreichbar</span> " + ", ".join(h(m) for m in ollama_status["modelle"][:6])) \
        if ollama_status["online"] else "<span class='badge low'>Ollama nicht erreichbar – Stufe 3/4-KI aus, Regeln laufen weiter</span>"
    return f"""
<section>
  <h2>Import</h2>
  <p class="muted">Reihenfolge: E-Rechnung (ZUGFeRD/XRechnung) → PDF-Text → Vision-OCR → Klassifizierung. Die erste Stufe, die greift, gewinnt. Nichts wird ohne Bestätigung verbucht.</p>
  <div id="dropzone" class="dropzone" tabindex="0">
    <strong>Belege hierher ziehen</strong> oder <label class="link">auswählen<input id="dateien" type="file" multiple accept=".pdf,.xml,.png,.jpg,.jpeg,.tif,.tiff,.webp,.heic" hidden></label>
    <div class="muted">PDF, XRechnung-XML, Fotos/Scans</div>
  </div>
  <div class="row">
    <label class="check"><input type="checkbox" id="ki" {"checked" if ki_an else ""}> KI-Stufen (Ollama) verwenden</label>
    <span>{ki}</span>
  </div>
  <table class="tabelle" id="import-tabelle"><thead><tr><th>Datei</th><th>Status</th><th>Stufe</th><th>Konfidenz</th><th>Meldung</th></tr></thead><tbody></tbody></table>

  <h3>Ordner importieren</h3>
  <form hx-post="/api/import/ordner" hx-target="#ordner-ergebnis" hx-include="#ki" class="row">
    <input name="pfad" placeholder="/Users/…/Downloads/Belege" size="50" required>
    <button>Alle Dateien im Ordner importieren</button>
  </form>
  <div id="ordner-ergebnis"></div>

  <h3>Kontoauszug importieren</h3>
  <form hx-post="/api/konto/import" hx-target="#konto-ergebnis" hx-encoding="multipart/form-data" class="row">
    <input type="file" name="datei" accept=".csv,.xml,.txt" required>
    <button>CSV / CAMT.053 einlesen und matchen</button>
  </form>
  <div id="konto-ergebnis"></div>
</section>
<script>
(function(){{
  const dz = document.getElementById('dropzone'), inp = document.getElementById('dateien');
  const tbody = document.querySelector('#import-tabelle tbody');
  async function senden(f){{
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>'+f.name.replace(/</g,'&lt;')+'</td><td colspan=4><span class="spinner"></span> wird verarbeitet…</td>';
    tbody.prepend(tr);
    const fd = new FormData(); fd.append('datei', f); fd.append('ki', document.getElementById('ki').checked ? '1' : '0');
    try {{
      const r = await fetch('/api/import', {{method:'POST', body: fd}});
      tr.outerHTML = await r.text();
    }} catch(e) {{ tr.children[1].textContent = 'Fehler: ' + e; }}
    document.dispatchEvent(new CustomEvent('zaehler-aktualisieren'));
  }}
  function alle(files){{ for (const f of files) senden(f); }}
  dz.addEventListener('dragover', e => {{ e.preventDefault(); dz.classList.add('aktiv'); }});
  dz.addEventListener('dragleave', () => dz.classList.remove('aktiv'));
  dz.addEventListener('drop', e => {{ e.preventDefault(); dz.classList.remove('aktiv'); alle(e.dataTransfer.files); }});
  inp.addEventListener('change', () => {{ alle(inp.files); inp.value=''; }});
}})();
</script>"""


def import_zeile(name: str, erg) -> str:
    cls = {"neu": "ok", "duplikat": "mid", "fehler": "low"}.get(erg.status, "")
    link = f' <a href="#" hx-get="/ui/pruefen/{erg.buchung_id}" hx-target="#main" hx-push-url="false">prüfen →</a>' if erg.buchung_id else ""
    return (f'<tr><td>{h(name)}</td><td><span class="badge {cls}">{h(erg.status)}</span></td>'
            f'<td>{stufe_badge(erg.stufe)}</td><td>{konf_badge(erg.konfidenz)}</td><td>{h(erg.meldung)}{link}</td></tr>')


# ------------------------------------------------------------- Prüfen

def pruefen_leer() -> str:
    return """<section><h2>Prüfen</h2><p class="ok-box">Keine offenen Vorschläge. Alles bestätigt.</p>
    <p><a href="#" hx-get="/ui/manuell" hx-target="#main">Buchung von Hand erfassen</a></p></section>"""


def pruefen_view(b: Buchung, beleg: Beleg | None, kategorien: list[Kategorie], offene: list[Buchung],
                 bw: Bewertung | None, extraktion: dict, cfg: dict) -> str:
    liste = "".join(
        f'<li class="{"aktiv" if x.id == b.id else ""}"><a href="#" hx-get="/ui/pruefen/{x.id}" hx-target="#main">'
        f'{konf_badge(x.konfidenz)} {h(d(x.datum))} · {h(x.lieferant or "?")} · {eur_fmt(x.betrag_brutto)}</a></li>'
        for x in offene[:60])
    vorschau = ""
    if beleg:
        if beleg.mime == "application/pdf" or beleg.dateipfad.lower().endswith(".pdf"):
            vorschau = f'<iframe class="vorschau" src="/beleg/{beleg.id}/datei#toolbar=0"></iframe>'
        elif beleg.mime.startswith("image/"):
            vorschau = f'<img class="vorschau" src="/beleg/{beleg.id}/datei" alt="Beleg">'
        else:
            vorschau = f'<pre class="vorschau">{h(json.dumps(extraktion, indent=1, ensure_ascii=False))}</pre>'
    else:
        vorschau = '<div class="vorschau muted">Kein Beleg hinterlegt (z. B. aus Kontobewegung angelegt).</div>'
    return f"""
<section class="pruefen">
  <aside>
    <h2>Prüfen <span class="muted">({len(offene)})</span></h2>
    <p class="muted">Niedrigste Konfidenz zuerst. <kbd>⏎</kbd> bestätigen &amp; weiter · <kbd>Esc</kbd> überspringen</p>
    <ul class="liste">{liste}</ul>
  </aside>
  <div class="vorschau-spalte">
    {vorschau}
    <div class="muted klein">Quelle: {stufe_badge(b.extraktion_stufe)} Klassifizierung: {h(b.klassifizierung_weg or "–")}
      {f' · Datei: <code>{h(beleg.dateipfad)}</code>' if beleg else ''}</div>
    <details><summary class="muted klein">Rohfelder der Extraktion</summary><pre class="klein">{h(json.dumps(extraktion, indent=1, ensure_ascii=False, default=str))}</pre></details>
  </div>
  <div class="formular-spalte">
    {buchung_formular(b, kategorien, cfg, action=f"/api/buchung/{b.id}/bestaetigen", bw=bw, naechste=True)}
  </div>
</section>"""


def buchung_formular(b: Buchung, kategorien: list[Kategorie], cfg: dict, action: str, bw: Bewertung | None = None,
                     naechste: bool = False, titel: str | None = None) -> str:
    m = json.loads(b.meta_json or "{}")
    opts = "".join(f'<option value="{k.id}" data-sonderfall="{h(k.sonderfall or "")}" data-richtung="{k.richtung}" {"selected" if k.id == b.kategorie_id else ""}>'
                   f'{h(k.name)}{f" (Zeile {k.eur_zeile})" if k.eur_zeile else ""}</option>' for k in kategorien)
    knopf = "Bestätigen &amp; weiter ⏎" if naechste else "Speichern"
    skip = f'<button type="button" class="sekundaer" hx-get="/ui/pruefen?ueberspringen={b.id}" hx-target="#main">Überspringen (Esc)</button>' if naechste and b.id else ""
    loeschen = f'<button type="button" class="gefahr" hx-post="/api/buchung/{b.id}/loeschen" hx-confirm="Buchung wirklich löschen? Der Beleg bleibt im Belegordner." hx-target="#main">Löschen</button>' if b.id else ""
    return f"""
<form id="buchung-form" hx-post="{action}" hx-target="#main" class="formular" autocomplete="off">
  <h3>{h(titel or "Buchung")} {konf_badge(b.konfidenz) if b.id else ""} {'<span class="badge rc">§13b</span>' if b.reverse_charge else ''}</h3>
  <div class="grid2">
    <label>Datum <input type="date" name="datum" value="{b.datum.isoformat()}" required autofocus></label>
    <label>Richtung <select name="richtung"><option value="ausgabe" {"selected" if b.richtung == "ausgabe" else ""}>Ausgabe</option><option value="einnahme" {"selected" if b.richtung == "einnahme" else ""}>Einnahme</option></select></label>
    <label class="breit">Lieferant / Kunde <input name="lieferant" value="{h(b.lieferant)}"></label>
    <label class="breit">Beschreibung <input name="beschreibung" value="{h(b.beschreibung)}"></label>
    <label>Rechnungsnr. <input name="rechnungsnummer" value="{h(b.rechnungsnummer)}"></label>
    <label>USt-IdNr. Lieferant <input name="ust_idnr" value="{h(b.ust_idnr)}" placeholder="z. B. IE6364992H"></label>
    <label>Netto <input type="number" step="0.01" name="betrag_netto" id="f_netto" value="{b.betrag_netto:.2f}"></label>
    <label>USt-Satz % <select name="ust_satz" id="f_satz">{''.join(f'<option value="{s}" {"selected" if float(s) == float(b.ust_satz) else ""}>{s} %</option>' for s in cfg["ust_saetze"])}</select></label>
    <label>USt-Betrag <input type="number" step="0.01" name="ust_betrag" id="f_ust" value="{b.ust_betrag:.2f}"></label>
    <label>Brutto <input type="number" step="0.01" name="betrag_brutto" id="f_brutto" value="{b.betrag_brutto:.2f}" required></label>
    <label class="breit">Kategorie <select name="kategorie_id" id="f_kat" required><option value="">– bitte wählen –</option>{opts}</select></label>
    <label class="breit check"><input type="checkbox" name="reverse_charge" value="1" {"checked" if b.reverse_charge else ""}> §13b Reverse-Charge (Steuerschuld liegt bei mir, UStVA Kz 46/47)</label>
  </div>
  <fieldset class="sonderfall" data-fuer="bewirtung"><legend>Bewirtung (Pflichtangaben)</legend>
    <label>Anlass <input name="meta_anlass" value="{h(str(m.get("anlass", "")))}"></label>
    <label>Teilnehmer <input name="meta_teilnehmer" value="{h(str(m.get("teilnehmer", "")))}"></label></fieldset>
  <fieldset class="sonderfall" data-fuer="fahrtkosten"><legend>Fahrtkosten</legend>
    <label>gefahrene km <input type="number" step="1" name="meta_km" value="{h(str(m.get("km", "")))}"></label> <span class="muted">× {cfg["km_pauschale"]:.2f} €</span></fieldset>
  <fieldset class="sonderfall" data-fuer="homeoffice"><legend>Homeoffice</legend>
    <label>Tage <input type="number" step="1" name="meta_tage" value="{h(str(m.get("tage", "")))}"></label> <span class="muted">× {cfg["homeoffice_tagespauschale"]:.2f} €, max. {cfg["homeoffice_max_jahr"]:.0f} €/Jahr</span></fieldset>
  <fieldset class="sonderfall" data-fuer="privatanteil"><legend>Privatanteil</legend>
    <label>Privatanteil % <input type="number" step="1" name="meta_privatanteil_prozent" value="{h(str(m.get("privatanteil_prozent", cfg["privatanteil_standard_prozent"])))}"></label></fieldset>
  <fieldset class="sonderfall" data-fuer="geschenk"><legend>Geschenk</legend>
    <label>Empfänger <input name="meta_empfaenger" value="{h(str(m.get("empfaenger", "")))}"></label> <span class="muted">Grenze {cfg["geschenk_grenze_je_empfaenger"]:.0f} € je Empfänger und Jahr</span></fieldset>
  <fieldset class="sonderfall" data-fuer="gwg afa"><legend>Wirtschaftsgut</legend>
    <label>Nutzungsdauer (Jahre) <input type="number" step="1" name="meta_nutzungsdauer_jahre" value="{h(str(m.get("nutzungsdauer_jahre", cfg["afa_nutzungsdauer_standard_jahre"])))}"></label>
    <span class="muted">GWG-Grenze {cfg["gwg_grenze_netto"]:.0f} € netto – darüber automatisch AfA</span></fieldset>
  {hinweise_html(b, bw)}
  <div class="row aktionen"><button type="submit">{knopf}</button> {skip} {loeschen}</div>
</form>
<script>
(function(){{
  const f = document.getElementById('buchung-form'); if (!f) return;
  const netto = f.querySelector('#f_netto'), satz = f.querySelector('#f_satz'), ust = f.querySelector('#f_ust'), brutto = f.querySelector('#f_brutto'), kat = f.querySelector('#f_kat');
  const r2 = x => Math.round(x * 100) / 100;
  netto.addEventListener('input', () => {{ const n = +netto.value || 0, s = +satz.value; ust.value = r2(n*s/100).toFixed(2); brutto.value = r2(n + n*s/100).toFixed(2); }});
  satz.addEventListener('change', () => {{ const b = +brutto.value || 0, s = +satz.value; const n = b/(1+s/100); netto.value = r2(n).toFixed(2); ust.value = r2(b-n).toFixed(2); }});
  brutto.addEventListener('input', () => {{ const b = +brutto.value || 0, s = +satz.value; const n = b/(1+s/100); netto.value = r2(n).toFixed(2); ust.value = r2(b-n).toFixed(2); }});
  function sonderfall(){{
    const opt = kat.options[kat.selectedIndex]; const sf = opt ? (opt.dataset.sonderfall || '') : '';
    f.querySelectorAll('.sonderfall').forEach(fs => fs.hidden = !fs.dataset.fuer.split(' ').includes(sf));
  }}
  kat.addEventListener('change', sonderfall); sonderfall();
  f.addEventListener('keydown', e => {{
    if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA' && !e.isComposing) {{ e.preventDefault(); f.requestSubmit(); }}
    if (e.key === 'Escape') {{ const s = f.querySelector('button.sekundaer'); if (s) s.click(); }}
  }});
}})();
</script>"""


def manuell_view(b: Buchung, kategorien: list[Kategorie], cfg: dict) -> str:
    return f'<section><h2>Manuell erfassen</h2><p class="muted">Von Hand erfasste Buchungen gelten als bestätigt – du bist die Quelle.</p>' \
           f'{buchung_formular(b, kategorien, cfg, action="/api/buchung/neu", titel="Neue Buchung")}</section>'


# ------------------------------------------------------------ Quartale

def quartale_view(ue: dict, modus: str, jahre: list[int], offene_vorschlaege: int, anlagen: list[Anlagegut]) -> str:
    def w(z: Zelle) -> float:
        return {"brutto": z.brutto, "netto": z.netto, "ust": z.ust, "abzugsfaehig": z.abzugsfaehig}[modus]

    jahr = ue["jahr"]
    tabs = "".join(
        f'<button class="{"aktiv" if modus == mo else ""}" hx-get="/ui/quartale?jahr={jahr}&modus={mo}" hx-target="#main">{name}</button>'
        for mo, name in (("brutto", "Brutto"), ("netto", "Netto"), ("ust", "USt-Spalte"), ("abzugsfaehig", "Abzugsfähig")))
    jahr_opts = "".join(f'<option value="{j}" {"selected" if j == jahr else ""}>{j}</option>' for j in jahre)
    zeilen = "".join(
        f'<tr class="{r["kategorie"].richtung}"><td>{h(r["kategorie"].name)}</td><td class="muted">{r["kategorie"].eur_zeile or "–"}</td>'
        + "".join(f'<td class="num">{eur_fmt(w(z))}</td>' for z in r["q"]) + f'<td class="num fett">{eur_fmt(w(r["jahr"]))}</td></tr>'
        for r in ue["zeilen"])
    summen = (
        f'<tr class="summe"><td>Summe Einnahmen</td><td></td>' + "".join(f'<td class="num">{eur_fmt(w(z))}</td>' for z in ue["einnahmen"]) + '</tr>'
        f'<tr class="summe"><td>Summe Ausgaben</td><td></td>' + "".join(f'<td class="num">{eur_fmt(w(z))}</td>' for z in ue["ausgaben"]) + '</tr>'
        f'<tr class="summe fett"><td>Gewinn (abzugsfähig)</td><td></td>' + "".join(f'<td class="num">{eur_fmt(g)}</td>' for g in ue["gewinn"]) + '</tr>')
    erkl = {
        "brutto": "Bei §19 ist der Bruttobetrag die Betriebsausgabe – das ist die maßgebliche Ansicht.",
        "netto": "Netto dient nur der Darstellung. So sähen die Ausgaben bei Regelbesteuerung mit Vorsteuerabzug aus.",
        "ust": "Ausgewiesene USt plus §13b-Steuer: das ist die Vorsteuer, die die Kleinunternehmerregelung pro Quartal kostet.",
        "abzugsfaehig": "Nach Sonderregeln (Bewirtung 70 %, Privatanteile, Deckel, Geschenke, GWG/AfA) – das fließt in die EÜR.",
    }[modus]
    ev = ue["entgangene_vorsteuer"]
    bestaetigt = sum(r["jahr"].anzahl for r in ue["zeilen"] if r["kategorie"].schluessel != "afa")
    quote = 100.0 * bestaetigt / (bestaetigt + offene_vorschlaege) if (bestaetigt + offene_vorschlaege) else 100.0
    anl = "".join(f'<tr><td>{h(a.bezeichnung)}</td><td>{d(a.anschaffung)}</td><td class="num">{eur_fmt(a.anschaffungskosten)}</td>'
                  f'<td><form hx-post="/api/anlage/{a.id}" hx-target="#main" class="inline"><input type="number" name="nutzungsdauer_jahre" value="{a.nutzungsdauer_jahre}" min="1" max="50" style="width:4em"> J. '
                  f'<input type="hidden" name="jahr" value="{jahr}"><button class="klein">ok</button></form></td>'
                  f'<td class="num">{eur_fmt(afa_fuer_jahr(a, jahr))}</td></tr>' for a in anlagen)
    return f"""
<section>
  <div class="row zwischen">
    <h2>Quartale <select hx-get="/ui/quartale?modus={modus}" hx-target="#main" name="jahr" hx-trigger="change">{jahr_opts}</select></h2>
    <div class="tabs">{tabs}</div>
  </div>
  <p class="muted">{erkl} {f'<span class="badge mid">{offene_vorschlaege} unbestätigte Vorschläge nicht enthalten</span>' if offene_vorschlaege else ''}</p>
  <div class="kpis">
    <div class="kpi gruen"><div class="l">Einnahmen {jahr}</div><div class="w">{eur_fmt(ue["einnahmen"][4].abzugsfaehig)}</div></div>
    <div class="kpi rot"><div class="l">Ausgaben (abzugsfähig)</div><div class="w">{eur_fmt(ue["ausgaben"][4].abzugsfaehig)}</div></div>
    <div class="kpi {"gruen" if ue["gewinn"][4] >= 0 else "rot"}"><div class="l">Gewinn</div><div class="w">{eur_fmt(ue["gewinn"][4])}</div></div>
    <div class="kpi gelb"><div class="l">Entgangene Vorsteuer (§19)</div><div class="w">{eur_fmt(ev[4])}</div></div>
    <div class="kpi"><div class="ring"><div class="kreis" style="--p:{quote}"><span>{quote:.0f} %</span></div><div><div class="l">Belege bestätigt</div><div class="fett">{bestaetigt} von {bestaetigt + offene_vorschlaege}</div></div></div></div>
  </div>
  <div class="scroll"><table class="tabelle"><thead><tr><th>Kategorie</th><th>Zeile</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>Jahr {jahr}</th></tr></thead>
  <tbody>{zeilen or '<tr><td colspan=7 class="muted">Noch keine bestätigten Buchungen in diesem Jahr.</td></tr>'}</tbody><tfoot>{summen}</tfoot></table></div>

  <div class="karte">
    <h3>Was-wäre-wenn: Was kostet §19 an Vorsteuer?</h3>
    <p class="muted">Bei Regelbesteuerung wäre diese USt (inkl. §13b-Steuer) als Vorsteuer abziehbar. Dagegen stünde USt-Pflicht auf eigene Rechnungen – Entscheidungsgrundlage, keine Empfehlung.</p>
    <table class="tabelle kompakt"><tr><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>Jahr</th></tr>
    <tr>{''.join(f'<td class="num">{eur_fmt(v)}</td>' for v in ev)}</tr></table>
  </div>

  <div class="row">
    <a class="button" href="/export/quartale.csv?jahr={jahr}&modus={modus}">CSV</a>
    <a class="button" href="/export/quartale.pdf?jahr={jahr}&modus={modus}" target="_blank">Druck-PDF</a>
  </div>

  <details {"open" if anlagen else ""}><summary>Anlagevermögen / AfA ({len(anlagen)})</summary>
    <table class="tabelle kompakt"><thead><tr><th>Bezeichnung</th><th>Anschaffung</th><th>Kosten</th><th>Nutzungsdauer</th><th>AfA {jahr}</th></tr></thead><tbody>{anl or '<tr><td colspan=5 class="muted">Keine Anlagegüter.</td></tr>'}</tbody></table>
  </details>
</section>"""


# --------------------------------------------------------- Offene Punkte

def _mail_link(m: MailFund) -> str:
    if m.link:
        return f'<a href="{h(m.link)}" target="_blank" rel="noopener">Link öffnen ↗</a>'
    return "Anhang importiert (Vorschlag)"


def offen_view(op: dict, kandidaten: dict[int, list[Buchung]], funde: list[MailFund], kategorien: dict[int, Kategorie]) -> str:
    def konto_zeile(k: Kontobewegung) -> str:
        kand = kandidaten.get(k.id, [])
        sel = "".join(f'<option value="{b.id}">{d(b.datum)} · {h(b.lieferant)} · {eur_fmt(b.betrag_brutto)}</option>' for b in kand)
        zuordnen = (f'<form class="inline" hx-post="/api/konto/{k.id}/zuordnen" hx-target="#main"><select name="buchung_id">{sel}</select><button class="klein">zuordnen</button></form>'
                    if kand else '<span class="muted klein">kein Kandidat</span>')
        return (f'<tr><td>{d(k.datum)}</td><td class="num {"neg" if k.betrag < 0 else "pos"}">{eur_fmt(k.betrag)}</td>'
                f'<td>{h(k.gegenkonto)}<div class="muted klein">{h(k.verwendungszweck[:120])}</div></td>'
                f'<td class="aktionen-zelle">{zuordnen} '
                f'<button class="klein" hx-post="/api/konto/{k.id}/buchung-anlegen" hx-target="#main" title="Buchung ohne Beleg anlegen (Beleg nachreichen)">Buchung anlegen</button> '
                f'<button class="klein sekundaer" hx-post="/api/konto/{k.id}/ignorieren" hx-target="#main" title="privat / nicht betrieblich">ignorieren</button></td></tr>')

    ohne_beleg = "".join(konto_zeile(k) for k in op["ohne_beleg"])
    ohne_konto = "".join(
        f'<tr><td>{d(b.datum)}</td><td class="num">{eur_fmt(b.betrag_brutto)}</td><td>{h(b.lieferant)} <span class="muted klein">{h(b.beschreibung[:60])}</span></td>'
        f'<td>{h(kategorien[b.kategorie_id].name) if b.kategorie_id in kategorien else "–"}</td><td><a href="#" hx-get="/ui/pruefen/{b.id}" hx-target="#main">öffnen</a></td></tr>'
        for b in op["ohne_konto"][:200])
    doppel = "".join(
        f'<tr><td>{d(a.datum)} / {d(b.datum)}</td><td class="num">{eur_fmt(a.betrag_brutto)}</td><td>{h(a.lieferant)} – {h(a.rechnungsnummer or "ohne Nr.")}</td>'
        f'<td><a href="#" hx-get="/ui/pruefen/{a.id}" hx-target="#main">#{a.id}</a> · <a href="#" hx-get="/ui/pruefen/{b.id}" hx-target="#main">#{b.id}</a></td></tr>'
        for a, b in op["doppel"])
    mail = "".join(
        f'<tr><td>{d(m.datum.date()) if m.datum else ""}</td><td>{h(m.absender)}</td><td>{h(m.betreff[:80])}</td>'
        f'<td>{_mail_link(m)}</td>'
        f'<td><button class="klein" hx-post="/api/mailfund/{m.id}/erledigt" hx-target="#main">erledigt</button> <button class="klein sekundaer" hx-post="/api/mailfund/{m.id}/ignoriert" hx-target="#main">ignorieren</button></td></tr>'
        for m in funde)
    return f"""
<section>
  <h2>Offene Punkte</h2>
  <div class="row"><button hx-post="/api/matching" hx-target="#main">Matching erneut laufen lassen</button></div>

  <h3>Beleg fehlt <span class="badge {"low" if op["ohne_beleg"] else "ok"}">{len(op["ohne_beleg"])}</span></h3>
  <p class="muted">Kontobewegungen ohne zugeordnete Buchung. Das ist die wichtigste Arbeitsliste: Beleg suchen und importieren, dann matcht es automatisch.</p>
  <div class="scroll"><table class="tabelle kompakt"><thead><tr><th>Datum</th><th>Betrag</th><th>Gegenkonto / Zweck</th><th>Aktion</th></tr></thead><tbody>{ohne_beleg or '<tr><td colspan=4 class="muted">Nichts offen.</td></tr>'}</tbody></table></div>

  <h3>Manuell holen <span class="badge {"mid" if funde else "ok"}">{len(funde)}</span></h3>
  <p class="muted">Mails, die nur einen Link zur Rechnung enthalten. Kein Login-Automatismus – Link öffnen, PDF laden, importieren.</p>
  <div class="scroll"><table class="tabelle kompakt"><thead><tr><th>Datum</th><th>Absender</th><th>Betreff</th><th>Link</th><th></th></tr></thead><tbody>{mail or '<tr><td colspan=5 class="muted">Keine offenen Mail-Funde.</td></tr>'}</tbody></table></div>

  <h3>Beleg ohne Kontobewegung <span class="badge">{len(op["ohne_konto"])}</span></h3>
  <p class="muted">Bar bezahlt, privat verauslagt oder Kontoauszug fehlt noch.</p>
  <div class="scroll"><table class="tabelle kompakt"><thead><tr><th>Datum</th><th>Brutto</th><th>Lieferant</th><th>Kategorie</th><th></th></tr></thead><tbody>{ohne_konto or '<tr><td colspan=5 class="muted">Alle Buchungen haben eine Kontobewegung.</td></tr>'}</tbody></table></div>

  <h3>Mögliche Doppelbuchungen <span class="badge {"low" if op["doppel"] else "ok"}">{len(op["doppel"])}</span></h3>
  <div class="scroll"><table class="tabelle kompakt"><thead><tr><th>Daten</th><th>Betrag</th><th>Lieferant / Nr.</th><th>Buchungen</th></tr></thead><tbody>{doppel or '<tr><td colspan=4 class="muted">Keine Auffälligkeiten.</td></tr>'}</tbody></table></div>
</section>"""


# -------------------------------------------------------- Jahresabschluss

def jahresabschluss_view(jahr: int, fragen: list[dict], status: dict[str, dict], kategorien: list[Kategorie], summen: dict[str, float], cfg: dict) -> str:
    bloecke = []
    for fr in fragen:
        st = status.get(fr["key"], {})
        kat = next((k for k in kategorien if k.schluessel == fr["kategorie"]), None)
        sf = kat.sonderfall if kat else None
        extra = ""
        if sf == "fahrtkosten":
            extra = '<input type="number" name="meta_km" placeholder="km" style="width:6em">'
        elif sf == "homeoffice":
            extra = '<input type="number" name="meta_tage" placeholder="Tage" style="width:6em">'
        elif sf == "privatanteil":
            extra = f'<input type="number" name="meta_privatanteil_prozent" value="{cfg["privatanteil_standard_prozent"]}" title="Privatanteil %" style="width:5em">%'
        bloecke.append(f"""
<div class="frage {"erledigt" if st.get("erledigt") else ""}">
  <div class="row zwischen">
    <label class="check"><input type="checkbox" hx-post="/api/fragebogen/{jahr}/{fr["key"]}/toggle" hx-target="#main" {"checked" if st.get("erledigt") else ""}> <strong>{h(fr["frage"])}</strong></label>
    <span class="muted">{h(kat.name) if kat else ""} · bisher {eur_fmt(summen.get(fr["kategorie"], 0.0))}</span>
  </div>
  <form class="row inline" hx-post="/api/buchung/neu" hx-target="#main">
    <input type="hidden" name="kategorie_id" value="{kat.id if kat else ""}"><input type="hidden" name="richtung" value="ausgabe"><input type="hidden" name="zurueck" value="jahresabschluss:{jahr}">
    <input type="hidden" name="ust_satz" value="{0 if sf in ("fahrtkosten", "homeoffice") else cfg["regelsteuersatz"]}">
    <input type="date" name="datum" value="{jahr}-12-31" required>
    <input name="lieferant" placeholder="Anbieter">
    <input name="beschreibung" placeholder="Beschreibung" size="24">
    <input type="number" step="0.01" name="betrag_brutto" placeholder="Brutto €" style="width:8em" {"" if sf in ("fahrtkosten", "homeoffice") else "required"}>
    {extra}
    <button class="klein">direkt erfassen</button>
  </form>
</div>""")
    erledigt = sum(1 for f in fragen if status.get(f["key"], {}).get("erledigt"))
    return f"""
<section>
  <h2>Jahresabschluss {jahr} <span class="badge {"ok" if erledigt == len(fragen) else "mid"}">{erledigt}/{len(fragen)} abgehakt</span></h2>
  <p class="muted">Geführter Fragebogen gegen die typischen vergessenen Posten. Pro Frage ein Feld zum Direkterfassen; Haken setzen, wenn geprüft.</p>
  {''.join(bloecke)}
  <p class="muted">Danach: <a href="#" hx-get="/ui/export?jahr={jahr}" hx-target="#main">Exporte für Elster</a>.</p>
</section>"""


# --------------------------------------------------------------- Export

def export_view(jahr: int, eur: list[dict], ustva_liste: list[dict], jahre: list[int]) -> str:
    jahr_opts = "".join(f'<option value="{j}" {"selected" if j == jahr else ""}>{j}</option>' for j in jahre)
    eur_html = "".join(f'<tr class="{"fett" if z["zeile"] is None else ""}"><td>{z["zeile"] or ""}</td><td>{h(z["bezeichnung"])}</td><td class="num">{eur_fmt(z["betrag"])}</td></tr>' for z in eur)
    ustva_html = ""
    for u in ustva_liste:
        if not u["positionen"]:
            ustva_html += f'<div class="karte"><h4>Q{u["quartal"]}</h4><p class="muted">Keine §13b-Positionen.</p></div>'
            continue
        kz = "".join(f'<tr><td>Kz {h(k)}</td><td class="num">{eur_fmt(v)}</td></tr>' for k, v in u["kennzahlen"].items())
        pos = "".join(f'<li>{d(p["buchung"].datum)} {h(p["buchung"].lieferant)} netto {eur_fmt(p["buchung"].betrag_netto)} → Kz {p["kz_basis"]}/{p["kz_steuer"]}: {eur_fmt(p["steuer"])}</li>' for p in u["positionen"])
        ustva_html += f'<div class="karte"><h4>Q{u["quartal"]} · Zahllast {eur_fmt(u["zahllast"])}</h4><table class="tabelle kompakt">{kz}</table><ul class="klein">{pos}</ul></div>'
    return f"""
<section>
  <h2>Export <select hx-get="/ui/export" hx-target="#main" name="jahr" hx-trigger="change">{jahr_opts}</select></h2>
  <p class="muted">Kein Elster-Direktversand – die Zahlen werden von Hand eingetragen. Nur bestätigte Buchungen fließen ein.</p>

  <h3>Anlage EÜR {jahr}</h3>
  <table class="tabelle kompakt"><thead><tr><th>Zeile</th><th>Bezeichnung</th><th>Betrag</th></tr></thead><tbody>{eur_html}</tbody></table>
  <div class="row"><a class="button" href="/export/eur.csv?jahr={jahr}">CSV</a> <a class="button" href="/export/eur.pdf?jahr={jahr}" target="_blank">PDF</a> <a class="button" href="/export/eur.json?jahr={jahr}">JSON</a></div>

  <h3>UStVA je Quartal – nur §13b</h3>
  <p class="muted">Als Kleinunternehmer entsteht eine UStVA-Pflicht nur für bezogene Leistungen mit Umkehr der Steuerschuld. Kz 46/47 (EU) bzw. 84/85 (Drittland). Einmalig fachlich prüfen lassen.</p>
  <div class="karten">{ustva_html}</div>

  <h3>Weitere Ausgaben</h3>
  <div class="row">
    <a class="button" href="/export/quartale.csv?jahr={jahr}&modus=brutto">Quartalstabelle CSV</a>
    <a class="button" href="/export/quartale.pdf?jahr={jahr}&modus=brutto" target="_blank">Quartalstabelle PDF</a>
    <a class="button" href="/export/belegjournal.csv?jahr={jahr}">Belegjournal CSV</a>
  </div>
</section>"""


# --------------------------------------------------------- Einstellungen

def einstellungen_view(ollama_status: dict, mail: dict, hat_pw: bool, regeln: list[Regel], kategorien: dict[int, Kategorie],
                       pfade: dict, meldung: str = "") -> str:
    regeln_html = "".join(
        f'<tr><td><code>{h(r.muster)}</code>{" <span class=muted>(regex)</span>" if r.ist_regex else ""}</td><td>{h(kategorien[r.kategorie_id].name) if r.kategorie_id in kategorien else "?"}</td>'
        f'<td>{r.prioritaet}</td><td>{"aus Korrektur" if r.erstellt_aus_korrektur else "manuell"}</td><td>{r.treffer}</td>'
        f'<td><button class="klein gefahr" hx-post="/api/regel/{r.id}/loeschen" hx-target="#main">löschen</button></td></tr>' for r in regeln)
    kat_opts = "".join(f'<option value="{k.id}">{h(k.name)}</option>' for k in sorted(kategorien.values(), key=lambda k: k.name))
    imap, emlx = mail["imap"], mail["emlx"]
    return f"""
<section>
  <h2>Einstellungen</h2>
  {f'<p class="ok-box">{h(meldung)}</p>' if meldung else ''}
  <div class="karte"><h3>Dateien</h3>
    <p>Datenbank: <code>{h(pfade["db"])}</code><br>Belegordner: <code>{h(pfade["belege"])}</code><br>Regeln &amp; Grenzwerte: <code>{h(pfade["regeln"])}</code>
    <button class="klein" hx-post="/api/config/reload" hx-target="#main">neu laden</button></p>
    <p class="muted">Sichern heißt: diese drei Dinge kopieren. Kein Cloud-Sync durch das Tool.</p></div>

  <div class="karte"><h3>Lokale KI (Ollama)</h3>
    <p>{"<span class='badge ok'>erreichbar</span> Modelle: " + (", ".join(h(m) for m in ollama_status["modelle"]) or "keine") if ollama_status["online"] else "<span class='badge low'>nicht erreichbar</span> – Stufe 3 (OCR) und KI-Klassifizierung sind aus; E-Rechnung, PDF-Text und Regeln funktionieren trotzdem."}</p>
    <p class="muted">Konfiguriert: Vision <code>{h(pfade["vision"])}</code>, Text <code>{h(pfade["text"])}</code>. Ändern in steuerregeln.json → ollama.</p></div>

  <div class="karte"><h3>Mail-Import A: IMAP (strikt readonly)</h3>
    <form hx-post="/api/mail/einstellungen" hx-target="#main" class="grid2">
      <label>Server <input name="imap_host" value="{h(imap.get("host", ""))}" placeholder="imap.gmail.com"></label>
      <label>Benutzer <input name="imap_user" value="{h(imap.get("user", ""))}" placeholder="name@example.org"></label>
      <label>Ordner <input name="imap_ordner" value="{h(imap.get("ordner", "Belege"))}"></label>
      <label>App-Passwort <input type="password" name="imap_passwort" placeholder="{"im Schlüsselbund hinterlegt" if hat_pw else "wird nur im macOS-Schlüsselbund gespeichert"}"></label>
      <label class="breit">Apple-Mail-Ordner (.emlx) <input name="emlx_pfad" value="{h(emlx.get("pfad", ""))}" size="50"></label>
      <label>Nur Mailboxen mit <input name="emlx_filter" value="{h(emlx.get("ordner_filter", ""))}" placeholder="Belege"></label>
      <div class="breit row"><button>Speichern</button></div>
    </form>
    <p class="muted">Empfehlung: Mailregel anlegen, die Rechnungsmails in einen Ordner „Belege“ sortiert. Gmail/iCloud brauchen ein app-spezifisches Passwort. Das Tool markiert nichts als gelesen, verschiebt und löscht nichts.</p>
    <div class="row">
      <button hx-post="/api/mail/imap" hx-target="#main" hx-indicator="#mail-spin">IMAP jetzt scannen</button>
      <button hx-post="/api/mail/emlx" hx-target="#main" hx-indicator="#mail-spin">Apple Mail lokal scannen</button>
      <span id="mail-spin" class="htmx-indicator spinner"></span>
    </div></div>

  <div class="karte"><h3>Regeln ({len(regeln)})</h3>
    <p class="muted">Lieferantenmuster → Kategorie. Werden vor jeder KI geprüft; jede Korrektur beim Prüfen legt automatisch eine an.</p>
    <table class="tabelle kompakt"><thead><tr><th>Muster</th><th>Kategorie</th><th>Prio</th><th>Herkunft</th><th>Treffer</th><th></th></tr></thead><tbody>{regeln_html or '<tr><td colspan=6 class="muted">Noch keine Regeln.</td></tr>'}</tbody></table>
    <form hx-post="/api/regel/neu" hx-target="#main" class="row inline">
      <input name="muster" placeholder="z. B. adobe oder ^df\\.eu" required> <select name="kategorie_id">{kat_opts}</select>
      <label class="check"><input type="checkbox" name="ist_regex" value="1"> Regex</label> <button class="klein">Regel anlegen</button>
    </form></div>
</section>"""


def meldung_box(text: str, cls: str = "ok-box") -> str:
    return f'<p class="{cls}">{h(text)}</p>'
