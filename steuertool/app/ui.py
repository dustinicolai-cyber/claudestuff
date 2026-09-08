"""HTML-Fragmente für HTMX. Reine Funktionen: Daten rein, HTML raus.
Kein Template-System, damit das Tool in zwei Jahren noch ohne Abhängigkeitspflege startet.
"""
from __future__ import annotations

import json
from datetime import date
from html import escape as h

from .export import eur_fmt
from .models import Anlagegut, Beleg, Buchung, IgnorRegel, Kategorie, Kontobewegung, MailFund, Regel
from .steuerlogik import Bewertung, Zelle, afa_fuer_jahr

ICON = {
    "check": '<svg viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg>',
    "pfeil": '<svg viewBox="0 0 24 24"><path d="M5 12h14m-6-6l6 6-6 6"/></svg>',
    "reload": '<svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5"/></svg>',
    "x": '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    "plus": '<svg viewBox="0 0 24 24"><path d="M12 5v14m-7-7h14"/></svg>',
    "minus": '<svg viewBox="0 0 24 24"><path d="M5 12h14"/></svg>',
    "stift": '<svg viewBox="0 0 24 24"><path d="M4 20h4l10.5-10.5a2 2 0 0 0 0-2.8l-1.2-1.2a2 2 0 0 0-2.8 0L4 16v4z"/><path d="M13 7l4 4"/></svg>',
    "upload": '<svg viewBox="0 0 24 24"><path d="M12 16V4m-5 5l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>',
    "datei_plus": '<svg viewBox="0 0 24 24"><path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/><path d="M12 11v6m-3-3h6"/></svg>',
    "auge_zu": '<svg viewBox="0 0 24 24"><path d="M3 3l18 18"/><path d="M10.6 10.6A2.5 2.5 0 0 0 13.4 13.4"/><path d="M9.9 5.2A10.4 10.4 0 0 1 12 5c5 0 8.5 4 9.5 7a13 13 0 0 1-2.8 3.9"/><path d="M6.6 6.6C4.6 8 3.2 10 2.5 12c1 3 4.5 7 9.5 7a9.7 9.7 0 0 0 4.1-.9"/></svg>',
    "sperren": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/></svg>',
    "link": '<svg viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.5 1.5"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.5-1.5"/></svg>',
    "unlink": '<svg viewBox="0 0 24 24"><path d="M15.7 8.3l3-3a4 4 0 0 0-5.7-5.7" transform="translate(0 4)"/><path d="M8.3 15.7l-3 3a4 4 0 0 0 5.7 5.7" transform="translate(0 -4)"/><path d="M4 4l16 16"/></svg>',
    "undo": '<svg viewBox="0 0 24 24"><path d="M4 10h11a5 5 0 0 1 0 10h-3"/><path d="M8 6l-4 4 4 4"/></svg>',
    "oeffnen": '<svg viewBox="0 0 24 24"><path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>',
}

STUFEN = {"zugferd": "E-Rechnung (XML)", "pdf": "PDF-Text", "ocr": "Vision-OCR", "manuell": "manuell", "keine": "keine", "kontoauszug": "Kontoauszug"}


def eur_zelle(x: float, cls: str = "") -> str:
    """Tabellenzelle: 0 als gedämpfter Strich, sonst Betrag; Minus steht immer explizit dabei."""
    if abs(x) < 0.005:
        return f'<td class="num leer{(" " + cls) if cls else ""}">–</td>'
    return f'<td class="num{(" " + cls) if cls else ""}">{eur_fmt(x)}</td>'


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
  <p class="muted erkl">Reihenfolge: E-Rechnung (ZUGFeRD/XRechnung) → PDF-Text → Vision-OCR → Klassifizierung. Die erste Stufe, die greift, gewinnt. Nichts wird ohne Bestätigung verbucht.</p>
  <div class="dropzonen">
    <div class="dropzone minus-zone" data-richtung="ausgabe" tabindex="0">
      <div class="dz-icon">{ICON["minus"]}</div>
      <strong>Ausgaben</strong><div class="muted">Eingangsrechnungen, Quittungen, Abos</div>
      <label class="link">Dateien auswählen<input type="file" multiple data-richtung="ausgabe" accept=".pdf,.xml,.png,.jpg,.jpeg,.tif,.tiff,.webp,.heic" hidden></label>
    </div>
    <div class="dropzone plus-zone" data-richtung="einnahme" tabindex="0">
      <div class="dz-icon">{ICON["plus"]}</div>
      <strong>Einnahmen</strong><div class="muted">Eigene Ausgangsrechnungen, Gutschriften</div>
      <label class="link">Dateien auswählen<input type="file" multiple data-richtung="einnahme" accept=".pdf,.xml,.png,.jpg,.jpeg,.tif,.tiff,.webp,.heic" hidden></label>
    </div>
  </div>
  <div class="row">
    <label class="check"><input type="checkbox" id="ki" {"checked" if ki_an else ""}> KI-Stufen (Ollama) verwenden</label>
    <span>{ki}</span>
  </div>
  <table class="tabelle" id="import-tabelle" hidden><thead><tr><th>Datei</th><th>Art</th><th>Status</th><th>Stufe</th><th>Konfidenz</th><th>Meldung</th></tr></thead><tbody></tbody></table>

  <h3>Ordner importieren</h3>
  <form hx-post="/api/import/ordner" hx-target="#ordner-ergebnis" hx-include="#ki" class="row" id="ordner-form">
    <label class="button btn-secondary" title="Ordner auswählen – die Dateien werden direkt hochgeladen">Ordner wählen …<input type="file" id="ordner-picker" webkitdirectory multiple hidden></label>
    <span class="muted">oder Pfad:</span>
    <input name="pfad" id="ordner-pfad" placeholder="/Users/…/Downloads/Belege" size="36" required>
    <select name="richtung" id="ordner-richtung"><option value="ausgabe">als Ausgaben</option><option value="einnahme">als Einnahmen</option></select>
    <button class="btn-primary">Alle Dateien im Ordner importieren</button>
  </form>
  <div id="ordner-ergebnis"></div>

  <hr class="trenner">
  <h3>Kontoauszug importieren</h3>
  <p class="muted erkl">Anderer Datentyp, andere Wirkung: Kontobewegungen werden mit Rechnungen abgeglichen, nicht als Belege gespeichert. Geht auch als PDF-Auszug der Bank (ING, Sparkasse …). Danach geht es unter „Kontoauszug“ weiter.</p>
  <form hx-post="/api/konto/import" hx-target="#konto-ergebnis" hx-encoding="multipart/form-data" class="row">
    <input type="file" name="datei" accept=".pdf,.csv,.xml,.txt" required>
    <button class="btn-secondary">PDF / CSV / CAMT.053 einlesen und abgleichen</button>
  </form>
  <div id="konto-ergebnis"></div>
</section>
<script>
(function(){{
  const tabelle = document.getElementById('import-tabelle'), tbody = tabelle.querySelector('tbody');
  const pfad = document.getElementById('ordner-pfad');
  try {{ pfad.value = localStorage.getItem('ordner-pfad') || ''; }} catch(e) {{}}
  document.getElementById('ordner-form').addEventListener('submit', () => {{ try {{ localStorage.setItem('ordner-pfad', pfad.value); }} catch(e) {{}} }});
  document.getElementById('ordner-picker').addEventListener('change', e => {{
    const richtung = document.getElementById('ordner-richtung').value;
    for (const f of e.target.files) if (/\.(pdf|xml|png|jpe?g|tiff?|webp|heic)$/i.test(f.name)) senden(f, richtung);
    e.target.value = '';
  }});
  async function senden(f, richtung){{
    tabelle.hidden = false;
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>'+f.name.replace(/</g,'&lt;')+'</td><td>'+(richtung === 'einnahme' ? 'Einnahme' : 'Ausgabe')+'</td><td colspan=4><span class="spinner"></span> wird verarbeitet…</td>';
    tbody.prepend(tr);
    const fd = new FormData(); fd.append('datei', f); fd.append('richtung', richtung); fd.append('ki', document.getElementById('ki').checked ? '1' : '0');
    try {{ const r = await fetch('/api/import', {{method:'POST', body: fd}}); tr.outerHTML = await r.text(); }}
    catch(e) {{ tr.children[2].textContent = 'Fehler: ' + e; }}
    document.dispatchEvent(new CustomEvent('zaehler-aktualisieren'));
  }}
  document.querySelectorAll('.dropzone').forEach(dz => {{
    const richtung = dz.dataset.richtung, inp = dz.querySelector('input[type=file]');
    dz.addEventListener('dragover', e => {{ e.preventDefault(); dz.classList.add('aktiv'); }});
    dz.addEventListener('dragleave', () => dz.classList.remove('aktiv'));
    dz.addEventListener('drop', e => {{ e.preventDefault(); dz.classList.remove('aktiv'); for (const f of e.dataTransfer.files) senden(f, richtung); }});
    inp.addEventListener('change', () => {{ for (const f of inp.files) senden(f, richtung); inp.value = ''; }});
  }});
}})();
</script>"""


def import_zeile(name: str, erg, richtung: str = "ausgabe") -> str:
    cls = {"neu": "ok", "duplikat": "mid", "fehler": "low"}.get(erg.status, "")
    link = f' <a href="#" hx-get="/ui/pruefen/{erg.buchung_id}" hx-target="#main" hx-push-url="false">prüfen →</a>' if erg.buchung_id else ""
    art = '<span class="plus">Einnahme</span>' if richtung == "einnahme" else '<span class="minus">Ausgabe</span>'
    return (f'<tr><td>{h(name)}</td><td>{art}</td><td><span class="badge {cls}">{h(erg.status)}</span></td>'
            f'<td>{stufe_badge(erg.stufe)}</td><td>{konf_badge(erg.konfidenz)}</td><td>{h(erg.meldung)}{link}</td></tr>')


# ------------------------------------------------------------- Prüfen

def _reiter_html(reiter: str, zaehler: dict) -> str:
    def t(r: str, name: str, cls: str) -> str:
        n = zaehler.get(r, 0)
        return (f'<button type="button" class="{"aktiv" if reiter == r else ""} {cls}" hx-get="/ui/pruefen?richtung={r}" hx-target="#main">'
                f'{name} <span class="z">{n}</span></button>')
    return f'<div class="tabs reiter">{t("ausgabe", "Ausgaben", "minus-tab")}{t("einnahme", "Einnahmen", "plus-tab")}</div>'


def lieferanten_datalist(namen: list[str]) -> str:
    """Alphabetische Vorschlagsliste für das Feld Lieferant/Kunde (ein Mal pro Seite)."""
    optionen = "".join(f'<option value="{h(n)}">' for n in namen)
    return f'<datalist id="lieferanten">{optionen}</datalist>'


def bestaetigt_zeile(b: Buchung, kategorien: list[Kategorie], mit_konto: set, gespeichert: bool = False) -> str:
    """Eine Zeile der Tabelle bestätigter Buchungen – die wichtigsten Felder direkt editierbar, Änderung speichert sofort."""
    opts = "".join(f'<option value="{k.id}" {"selected" if k.id == b.kategorie_id else ""}>{h(k.name)}</option>'
                   for k in kategorien if k.richtung == b.richtung)
    konto = '<span class="badge ok" title="Kontobewegung zugeordnet">Konto ✓</span>' if b.id in mit_konto else '<span class="muted klein">–</span>'
    return (f'<tr id="bz-{b.id}" class="bz {"gespeichert" if gespeichert else ""}" data-datum="{b.datum.isoformat()}" data-betrag="{b.betrag_brutto:.2f}" data-lieferant="{h((b.lieferant or "").lower())}" '
            f'hx-post="/api/buchung/{b.id}/schnell" hx-trigger="change" hx-include="closest tr" hx-target="this" hx-swap="outerHTML">'
            f'<td><input type="date" name="datum" value="{b.datum.isoformat()}" aria-label="Datum"></td>'
            f'<td><span class="badge {"plus-b" if b.richtung == "einnahme" else "minus-b"}">{"Einnahme" if b.richtung == "einnahme" else "Ausgabe"}</span></td>'
            f'<td><input name="lieferant" list="lieferanten" value="{h(b.lieferant)}" placeholder="Lieferant / Kunde" aria-label="Lieferant / Kunde"></td>'
            f'<td><input name="beschreibung" value="{h(b.beschreibung)}" placeholder="–" aria-label="Beschreibung"></td>'
            f'<td><select name="kategorie_id" aria-label="Kategorie">{opts}</select></td>'
            f'<td class="num"><input type="number" step="0.01" name="betrag_brutto" value="{b.betrag_brutto:.2f}" aria-label="Brutto in Euro"></td>'
            f'<td>{konto}</td>'
            f'<td class="aktionen-zelle"><a href="#" class="btn-ghost" hx-get="/ui/pruefen/{b.id}" hx-target="#main" title="Alle Felder mit Belegvorschau bearbeiten">{ICON["stift"]}Bearbeiten</a></td></tr>')


def bestaetigte_tabelle(buchungen: list[Buchung], kategorien: list[Kategorie], mit_konto: set, jahr: int | None, lieferanten: list[str], datalist: bool = True) -> str:
    """Volle Breite: alle eingecheckten Buchungen des Jahres, Kernfelder direkt in der Zeile änderbar, Stift für die komplette Maske."""
    rows = "".join(bestaetigt_zeile(b, kategorien, mit_konto) for b in buchungen)
    return f"""
<section class="bestaetigt-tabelle" id="bestaetigt-tabelle">
  <div class="row zwischen"><h3>Bestätigte Buchungen <span class="z">{len(buchungen)}</span>{f' <span class="muted klein">{jahr}</span>' if jahr else ''}</h3>
    <span class="row" style="margin:0;gap:.8rem"><input type="search" class="listen-suche" placeholder="in der Liste suchen …" aria-label="Bestätigte durchsuchen"><span class="muted klein listen-zaehler"></span></span></div>
  <p class="muted klein">Datum, Kunde, Beschreibung, Kategorie und Brutto direkt in der Zeile ändern – wird beim Verlassen des Felds gespeichert. Der Stift öffnet die komplette Maske mit Belegvorschau.</p>
  {lieferanten_datalist(lieferanten) if datalist else ''}
  <div class="scroll"><table class="tabelle kompakt bz-tabelle"><colgroup><col class="c-datum"><col class="c-art"><col class="c-lief"><col class="c-besch"><col class="c-kat"><col class="c-brutto"><col class="c-konto"><col class="c-aktion"></colgroup>
    <thead><tr><th class="sortierbar" data-sort="datum" title="nach Datum sortieren">Datum <span class="pfeil"></span></th><th>Art</th><th class="sortierbar" data-sort="lieferant" title="alphabetisch sortieren">Lieferant / Kunde <span class="pfeil"></span></th><th>Beschreibung</th><th>Kategorie</th><th class="num sortierbar" data-sort="betrag" title="nach Betrag sortieren">Brutto € <span class="pfeil"></span></th><th>Konto</th><th></th></tr></thead>
    <tbody>{rows or '<tr><td colspan=8 class="muted">Noch nichts bestätigt.</td></tr>'}</tbody></table></div>
  <script>
  (function(){{
    const box = document.getElementById('bestaetigt-tabelle'), tbody = box.querySelector('tbody'), suche = box.querySelector('.listen-suche'), zaehler = box.querySelector('.listen-zaehler');
    const zeilen = () => [...tbody.querySelectorAll('tr.bz')];
    const speicher = {{ lesen(){{ try {{ return JSON.parse(sessionStorage.getItem('bestaetigt-zustand') || '{{}}'); }} catch (e) {{ return {{}}; }} }},
                       schreiben(z){{ try {{ sessionStorage.setItem('bestaetigt-zustand', JSON.stringify(z)); }} catch (e) {{}} }} }};
    const zustand = speicher.lesen();
    function filtern(){{ const q = (suche.value || '').trim().toLowerCase(); let n = 0;
      zeilen().forEach(tr => {{ const t = [...tr.querySelectorAll('input,select')].map(e => e.tagName === 'SELECT' ? e.options[e.selectedIndex]?.text : e.value).join(' ').toLowerCase();
        const ok = !q || t.includes(q); tr.hidden = !ok; if (ok) n++; }});
      zaehler.textContent = q ? n + ' von ' + zeilen().length : ''; }}
    suche.addEventListener('input', () => {{ filtern(); zustand.suche = suche.value; speicher.schreiben(zustand); }});
    let sortKey = null, sortDir = -1;
    const vgl = (a, b, key) => {{ const va = a.dataset[key], vb = b.dataset[key]; return key === 'betrag' ? (+va - +vb) : (va < vb ? -1 : va > vb ? 1 : 0); }};
    function sortieren(key, dir){{ sortKey = key; sortDir = dir; const rows = zeilen(); rows.sort((a, b) => vgl(a, b, key) * dir || -vgl(a, b, 'datum')); rows.forEach(r => tbody.appendChild(r));
      box.querySelectorAll('th.sortierbar').forEach(t => {{ const an = t.dataset.sort === key; t.classList.toggle('aktiv', an); t.querySelector('.pfeil').textContent = an ? (dir > 0 ? '▲' : '▼') : ''; }}); }}
    box.querySelectorAll('th.sortierbar').forEach(th => th.addEventListener('click', () => {{ const key = th.dataset.sort; sortieren(key, sortKey === key ? -sortDir : (key === 'datum' ? -1 : 1)); zustand.sort = key; zustand.dir = sortDir; speicher.schreiben(zustand); }}));
    if (zustand.suche) {{ suche.value = zustand.suche; filtern(); }}
    if (zustand.sort) sortieren(zustand.sort, zustand.dir || 1);
    // Enter im Feld = speichern (change) statt Formular-Submit
    box.addEventListener('keydown', e => {{ if (e.key === 'Enter' && e.target.matches('input')) {{ e.preventDefault(); e.target.blur(); }} }});
  }})();
  </script>
</section>"""


def pruefen_leer(reiter: str = "ausgabe", zaehler: dict | None = None, bestaetigte: list[Buchung] | None = None,
                 kategorien: list[Kategorie] | None = None, mit_konto: set | None = None, jahr: int | None = None, lieferanten: list[str] | None = None) -> str:
    zaehler = zaehler or {}
    andere = "einnahme" if reiter == "ausgabe" else "ausgabe"
    hinweis = (f'<p class="muted">Im Reiter {"Einnahmen" if andere == "einnahme" else "Ausgaben"} warten noch {zaehler.get(andere, 0)} Vorschläge.</p>'
               if zaehler.get(andere) else '<p class="muted">Alles bestätigt.</p>')
    return f"""<section class="pruefen-leer"><div class="row zwischen"><h2>Prüfen</h2>{_reiter_html(reiter, zaehler)}</div>
    <p class="ok-box"><span>Keine offenen {"Einnahmen" if reiter == "einnahme" else "Ausgaben"}-Vorschläge.</span></p>{hinweis}
    <p><a href="#" hx-get="/ui/manuell" hx-target="#main">Buchung von Hand erfassen</a></p></section>
{bestaetigte_tabelle(bestaetigte or [], kategorien or [], mit_konto or set(), jahr, lieferanten or [])}"""


def pruefen_view(b: Buchung, beleg: Beleg | None, kategorien: list[Kategorie], offene: list[Buchung],
                 bw: Bewertung | None, extraktion: dict, cfg: dict, reiter: str = "ausgabe", zaehler: dict | None = None,
                 bestaetigte: list[Buchung] | None = None, mit_konto: set | None = None, jahr: int | None = None,
                 lieferanten: list[str] | None = None) -> str:
    zaehler = zaehler or {}
    korrektur = b.status == "bestaetigt"
    liste = "".join(
        f'<li class="{"aktiv" if x.id == b.id else ""}"><input type="checkbox" name="ids" value="{x.id}" aria-label="auswählen">'
        f'<a href="#" hx-get="/ui/pruefen/{x.id}" hx-target="#main">'
        f'{konf_badge(x.konfidenz)} {h(d(x.datum))} · {h(x.lieferant or "?")} · {eur_fmt(x.betrag_brutto)}</a></li>'
        for x in offene[:200] if x.status == "vorschlag")
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
    <div class="row zwischen"><h2>Prüfen</h2></div>
    {_reiter_html(reiter, zaehler)}
    <p class="muted klein">Niedrigste Konfidenz zuerst. <kbd>⏎</kbd> bestätigen &amp; weiter · <kbd>Esc</kbd> überspringen</p>
    <form id="pruef-liste" hx-post="/api/buchungen/loeschen" hx-target="#main" hx-confirm="Ausgewählte Buchungen löschen? Die Belegdateien wandern in Belege/Papierkorb.">
      <div class="row zwischen listen-leiste">
        <label class="check klein"><input type="checkbox" id="alle-waehlen"> alle</label>
        <span><button type="button" class="klein outline-orange auswahl-aktion" disabled hx-post="/api/buchungen/neu-erkennen" hx-include="#pruef-liste" hx-target="#main" title="Extraktion mit den aktuellen Regeln wiederholen">{ICON["reload"]}Neu erkennen</button>
        <button type="submit" class="klein outline-rot auswahl-aktion" id="auswahl-loeschen" disabled>{ICON["x"]}Löschen (0)</button></span>
      </div>
      <ul class="liste">{liste}</ul>
    </form>
    <script>
    (function(){{
      const f = document.getElementById('pruef-liste'), alle = document.getElementById('alle-waehlen'), knopf = document.getElementById('auswahl-loeschen');
      const boxen = () => [...f.querySelectorAll('input[name=ids]')];
      function zaehlen(){{ const n = boxen().filter(b => b.checked).length; f.querySelectorAll('.auswahl-aktion').forEach(k => k.disabled = !n); knopf.lastChild.textContent = 'Löschen (' + n + ')'; }}
      alle.addEventListener('change', () => {{ boxen().forEach(b => b.checked = alle.checked); zaehlen(); }});
      f.addEventListener('change', e => {{ if (e.target.name === 'ids') zaehlen(); }});
      let letzte = null;
      f.addEventListener('click', e => {{ if (e.target.name !== 'ids') return; const b = boxen(); const i = b.indexOf(e.target);
        if (e.shiftKey && letzte !== null) {{ const [a, z] = [Math.min(i, letzte), Math.max(i, letzte)]; for (let k = a; k <= z; k++) b[k].checked = e.target.checked; zaehlen(); }} letzte = i; }});
    }})();
    </script>
  </aside>
  <div class="vorschau-spalte">
    {vorschau}
    <div class="muted klein">Quelle: {stufe_badge(b.extraktion_stufe)} Klassifizierung: {h(b.klassifizierung_weg or "–")}
      {f' · Datei: <code>{h(beleg.dateipfad)}</code>' if beleg else ''}</div>
    <details><summary class="muted klein">Rohfelder der Extraktion</summary><pre class="klein">{h(json.dumps(extraktion, indent=1, ensure_ascii=False, default=str))}</pre></details>
  </div>
  <div class="formular-spalte">
    {buchung_formular(b, kategorien, cfg, action=f"/api/buchung/{b.id}/bestaetigen", bw=bw, naechste=not korrektur, lieferanten=lieferanten)}
  </div>
</section>
{bestaetigte_tabelle(bestaetigte or [], kategorien, mit_konto or set(), jahr, lieferanten or [], datalist=False)}"""


def buchung_formular(b: Buchung, kategorien: list[Kategorie], cfg: dict, action: str, bw: Bewertung | None = None,
                     naechste: bool = False, titel: str | None = None, lieferanten: list[str] | None = None) -> str:
    m = json.loads(b.meta_json or "{}")
    opts = "".join(f'<option value="{k.id}" data-sonderfall="{h(k.sonderfall or "")}" data-richtung="{k.richtung}" {"selected" if k.id == b.kategorie_id else ""}>'
                   f'{h(k.name)}{f" (Zeile {k.eur_zeile})" if k.eur_zeile else ""}</option>' for k in kategorien)
    korrektur = bool(b.id) and b.status == "bestaetigt"
    knopf = "Beleg OK" if naechste else ("Korrektur speichern" if korrektur else "Speichern")
    skip = f'<button type="button" class="outline-gelb" hx-get="/ui/pruefen?ueberspringen={b.id}&richtung={b.richtung}" hx-target="#main" title="Überspringen (Esc)">{ICON["pfeil"]}Überspringen</button>' if naechste and b.id else ""
    neu_erkennen = f'<button type="button" class="outline-orange" hx-post="/api/buchung/{b.id}/neu-erkennen" hx-target="#main" title="Felder aus der Belegdatei neu ziehen">{ICON["reload"]}Neu laden</button>' if b.id and b.beleg_id and b.status == "vorschlag" else ""
    loeschen = f'<button type="button" class="outline-rot" hx-post="/api/buchung/{b.id}/loeschen" hx-confirm="Buchung wirklich löschen? Die Belegdatei wandert nach Belege/Papierkorb." hx-target="#main">{ICON["x"]}Löschen</button>' if b.id else ""
    if titel is None:
        titel = (b.lieferant or "Unbekannter Beleg") if b.id else "Neue Buchung"
    fremd_txt = f' <span class="muted">({b.betrag_fremd:,.2f} $)</span>'.replace(",", "X").replace(".", ",").replace("X", ".") if b.waehrung == "USD" and b.betrag_fremd else ""
    untertitel = f'{h(d(b.datum))} · <span class="{"plus" if b.richtung == "einnahme" else "minus"}">{eur_fmt(b.betrag_brutto)}</span>{fremd_txt}' if b.id else ""
    beschreibung_kopf = f"""<div class="kopf-beschreibung">
        <span class="txt {"leer" if not b.beschreibung else ""}">{h(b.beschreibung) if b.beschreibung else "Beschreibung hinzufügen"}</span>
        <button type="button" class="stift" title="Beschreibung bearbeiten" aria-label="Beschreibung bearbeiten">{ICON["stift"]}</button>
        <input name="beschreibung" value="{h(b.beschreibung)}" placeholder="Beschreibung" hidden>
      </div>"""
    return f"""
<form id="buchung-form" hx-post="{action}" hx-target="#main" class="formular" autocomplete="off">
  <div class="formular-kopf">
    <div class="kopf-titel">
      <h2>{h(titel)} {'<span class="badge ok">bestätigt</span>' if korrektur else (konf_badge(b.konfidenz) if b.id else "")} {'<span class="badge rc">§13b</span>' if b.reverse_charge else ''}</h2>
      <div class="muted klein">{untertitel}</div>
      {beschreibung_kopf}
    </div>
    <div class="aktionen aktionen-raster {"zwei" if korrektur else ""}"><button type="submit" class="gruen" title="{"Korrektur speichern" if korrektur else "Bestätigen und weiter (⏎)"}">{ICON["check"]}{knopf}</button>{skip}{neu_erkennen}{loeschen}</div>
  </div>
  <div class="grid2">
    <label>Datum <input type="date" name="datum" value="{b.datum.isoformat()}" required autofocus></label>
    <label>Richtung <select name="richtung"><option value="ausgabe" {"selected" if b.richtung == "ausgabe" else ""}>Ausgabe</option><option value="einnahme" {"selected" if b.richtung == "einnahme" else ""}>Einnahme</option></select></label>
    <label class="breit">Lieferant / Kunde <input name="lieferant" list="lieferanten" value="{h(b.lieferant)}" placeholder="tippen oder aus der Liste wählen"></label>
    {lieferanten_datalist(lieferanten) if lieferanten is not None else ''}
    <label>Rechnungsnr. <input name="rechnungsnummer" value="{h(b.rechnungsnummer)}"></label>
    <label>USt-IdNr. Lieferant <input name="ust_idnr" value="{h(b.ust_idnr)}" placeholder="z. B. IE6364992H"></label>
    <label>Netto <input type="number" step="0.01" name="betrag_netto" id="f_netto" value="{b.betrag_netto:.2f}"></label>
    <label>USt-Satz % <select name="ust_satz" id="f_satz">{''.join(f'<option value="{s}" {"selected" if float(s) == float(b.ust_satz) else ""}>{s} %</option>' for s in cfg["ust_saetze"])}</select></label>
    <label>USt-Betrag <input type="number" step="0.01" name="ust_betrag" id="f_ust" value="{b.ust_betrag:.2f}"></label>
    <label>Brutto in € <input type="number" step="0.01" name="betrag_brutto" id="f_brutto" value="{b.betrag_brutto:.2f}" required></label>
    <label>Währung der Rechnung <select name="waehrung" id="f_waehrung"><option value="EUR" {"selected" if b.waehrung == "EUR" else ""}>EUR €</option><option value="USD" {"selected" if b.waehrung == "USD" else ""}>USD $</option></select></label>
    <label class="fremd" {"hidden" if b.waehrung == "EUR" else ""}>Rechnungsbetrag in $ <input type="number" step="0.01" name="betrag_fremd" id="f_fremd" value="{b.betrag_fremd:.2f}"></label>
    <div class="breit fremd muted klein" {"hidden" if b.waehrung == "EUR" else ""} id="f_kurs">Brutto in € ist der tatsächlich abgebuchte Betrag (Kontoauszug). Netto/USt werden daraus gerechnet.</div>
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
  const waehrung = f.querySelector('#f_waehrung'), fremd = f.querySelector('#f_fremd'), kurs = f.querySelector('#f_kurs');
  function waehrungAnzeigen(){{
    const usd = waehrung.value === 'USD';
    f.querySelectorAll('.fremd').forEach(x => x.hidden = !usd);
    if (usd) {{ const u = +fremd.value || 0, e = +brutto.value || 0; kurs.textContent = (u && e) ? `Kurs ${{(u / e).toFixed(4)}} $ je € · Brutto in € ist der tatsächlich abgebuchte Betrag (Kontoauszug).` : 'Brutto in € ist der tatsächlich abgebuchte Betrag (Kontoauszug). Netto/USt werden daraus gerechnet.'; }}
  }}
  waehrung.addEventListener('change', () => {{ if (waehrung.value === 'USD' && !(+fremd.value)) fremd.value = brutto.value; waehrungAnzeigen(); }});
  fremd.addEventListener('input', waehrungAnzeigen); brutto.addEventListener('input', waehrungAnzeigen); waehrungAnzeigen();
  const kb = f.querySelector('.kopf-beschreibung');
  if (kb) {{
    const txt = kb.querySelector('.txt'), inp = kb.querySelector('input'), stift = kb.querySelector('.stift');
    function oeffnen(){{ txt.hidden = true; stift.hidden = true; inp.hidden = false; inp.focus(); inp.select(); }}
    function schliessen(){{ inp.hidden = true; txt.hidden = false; stift.hidden = false; const v = inp.value.trim(); txt.textContent = v || 'Beschreibung hinzufügen'; txt.classList.toggle('leer', !v); }}
    stift.addEventListener('click', oeffnen); txt.addEventListener('click', oeffnen);
    inp.addEventListener('blur', schliessen);
    inp.addEventListener('keydown', e => {{ if (e.key === 'Enter' || e.key === 'Escape') {{ e.preventDefault(); e.stopPropagation(); inp.blur(); }} }});
  }}
  f.addEventListener('keydown', e => {{
    if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA' && !e.isComposing) {{ e.preventDefault(); f.requestSubmit(); }}
    if (e.key === 'Escape') {{ const s = f.querySelector('button.outline-gelb'); if (s) s.click(); }}
  }});
}})();
</script>"""


def manuell_view(b: Buchung, kategorien: list[Kategorie], cfg: dict, lieferanten: list[str] | None = None) -> str:
    return f'<section><p class="muted erkl">Von Hand erfasste Buchungen gelten als bestätigt – du bist die Quelle.</p>' \
           f'{buchung_formular(b, kategorien, cfg, action="/api/buchung/neu", titel="Neue Buchung", lieferanten=lieferanten or [])}</section>'


# ------------------------------------------------------------ Quartale

def quartale_view(ue: dict, modus: str, jahre: list[int], offene_vorschlaege: int, anlagen: list[Anlagegut]) -> str:
    def w(z: Zelle) -> float:
        return {"brutto": z.brutto, "netto": z.netto, "ust": z.ust, "abzugsfaehig": z.abzugsfaehig}[modus]

    jahr = ue["jahr"]
    tabs = "".join(
        f'<button class="{"aktiv" if modus == mo else ""}" hx-get="/ui/quartale?jahr={jahr}&modus={mo}" hx-target="#main">{name}</button>'
        for mo, name in (("brutto", "Brutto"), ("netto", "Netto"), ("ust", "USt-Spalte"), ("abzugsfaehig", "Abzugsfähig")))
    zeilen = "".join(
        f'<tr><td>{h(r["kategorie"].name)}</td><td class="muted">{r["kategorie"].eur_zeile or "–"}</td>'
        + "".join(eur_zelle(w(z)) for z in r["q"]) + eur_zelle(w(r["jahr"]), "fett") + '</tr>'
        for r in ue["zeilen"])
    summen = (
        f'<tr class="summe"><td>Summe Einnahmen</td><td></td>' + "".join(eur_zelle(w(z)) for z in ue["einnahmen"]) + '</tr>'
        f'<tr class="summe"><td>Summe Ausgaben</td><td></td>' + "".join(eur_zelle(w(z)) for z in ue["ausgaben"]) + '</tr>'
        f'<tr class="summe fett"><td>Gewinn / Verlust</td><td></td>' + "".join(eur_zelle(g, "plus" if g >= 0 else "minus") for g in ue["gewinn"]) + '</tr>')
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
                  f'<input type="hidden" name="jahr" value="{jahr}"><button class="klein btn-secondary">ok</button></form></td>'
                  f'<td class="num">{eur_fmt(afa_fuer_jahr(a, jahr))}</td></tr>' for a in anlagen)
    return f"""
<section>
  <div class="row zwischen">
    <p class="muted erkl">{erkl}</p>
    <div class="tabs">{tabs}</div>
  </div>
  <p class="muted"> {f'<span class="badge mid">{offene_vorschlaege} unbestätigte Vorschläge nicht enthalten</span>' if offene_vorschlaege else ''}</p>
  <div class="kpis">
    <div class="kpi"><div class="l">Einnahmen {jahr}</div><div class="w">{eur_fmt(ue["einnahmen"][4].abzugsfaehig)}</div></div>
    <div class="kpi"><div class="l">Ausgaben (abzugsfähig)</div><div class="w">{eur_fmt(ue["ausgaben"][4].abzugsfaehig)}</div></div>
    <div class="kpi {"gruen" if ue["gewinn"][4] >= 0 else "rot"}"><div class="l">{"Gewinn" if ue["gewinn"][4] >= 0 else "Verlust"}</div><div class="w">{eur_fmt(ue["gewinn"][4])}</div></div>
    <div class="kpi gelb"><div class="l">Entgangene Vorsteuer (§19)</div><div class="w">{eur_fmt(ev[4])}</div></div>
    <div class="kpi"><div class="ring"><div class="kreis" style="--p:{quote}"><span>{quote:.0f} %</span></div><div><div class="l">Belege bestätigt</div><div class="fett">{bestaetigt} von {bestaetigt + offene_vorschlaege}</div></div></div></div>
  </div>
  <div class="scroll"><table class="tabelle"><thead><tr><th>Kategorie</th><th>Zeile</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>Jahr {jahr}</th></tr></thead>
  <tbody>{zeilen or '<tr><td colspan=7 class="muted">Noch keine bestätigten Buchungen in diesem Jahr.</td></tr>'}</tbody><tfoot>{summen}</tfoot></table></div>

  <div class="karte">
    <h3>Was-wäre-wenn: Was kostet §19 an Vorsteuer?</h3>
    <p class="muted">Bei Regelbesteuerung wäre diese USt (inkl. §13b-Steuer) als Vorsteuer abziehbar. Dagegen stünde USt-Pflicht auf eigene Rechnungen – Entscheidungsgrundlage, keine Empfehlung.</p>
    <table class="tabelle kompakt"><tr><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>Jahr</th></tr>
    <tr>{''.join(eur_zelle(v, "neutral") for v in ev)}</tr></table>
  </div>

  <div class="row">
    <a class="button btn-secondary" href="/export/quartale.csv?jahr={jahr}&modus={modus}">CSV</a>
    <a class="button btn-secondary" href="/export/quartale.pdf?jahr={jahr}&modus={modus}" target="_blank">Druck-PDF</a>
  </div>

  <details {"open" if anlagen else ""}><summary>Anlagevermögen / AfA ({len(anlagen)})</summary>
    <table class="tabelle kompakt"><thead><tr><th>Bezeichnung</th><th>Anschaffung</th><th>Kosten</th><th>Nutzungsdauer</th><th>AfA {jahr}</th></tr></thead><tbody>{anl or '<tr><td colspan=5 class="muted">Keine Anlagegüter.</td></tr>'}</tbody></table>
  </details>
</section>"""


# --------------------------------------------------------- Offene Punkte

def _mail_link(m: MailFund) -> str:
    if m.link:
        return f'<a href="{h(m.link)}" target="_blank" rel="noopener">Rechnung laden ↗</a>'
    return "Anhang importiert (Vorschlag)"


def _sektion(titel: str, anzahl: int, leer: str, inhalt: str, farbe: str = "mid", rechts: str = "") -> str:
    """Leere Sektionen: eine Zeile, kein Tabellenkopf."""
    if anzahl == 0:
        return f'<div class="sektion leer"><span class="badge ok">✓</span> <strong>{h(titel)}</strong> <span class="muted">– {h(leer)}</span></div>'
    return f'<div class="sektion"><div class="row zwischen"><h3>{h(titel)} <span class="badge {farbe}">{anzahl}</span></h3>{rechts}</div>{inhalt}</div>'


def offen_view(op: dict, kandidaten: dict[int, list[Buchung]], funde: list[MailFund], kategorien: dict[int, Kategorie]) -> str:
    def konto_zeile(k: Kontobewegung) -> str:
        kand = kandidaten.get(k.id, [])
        sel = "".join(f'<option value="{b.id}">{d(b.datum)} · {h(b.lieferant)} · {eur_fmt(b.betrag_brutto)}</option>' for b in kand)
        zuordnen = (f'<form class="inline" hx-post="/api/konto/{k.id}/zuordnen" hx-target="#main"><select name="buchung_id">{sel}</select><button class="klein btn-secondary">zuordnen</button></form>'
                    if kand else '<span class="muted klein">kein Kandidat</span>')
        return (f'<tr><td>{d(k.datum)}</td><td class="num">{eur_fmt(k.betrag)}</td>'
                f'<td>{h(k.gegenkonto)}<div class="muted klein">{h(k.verwendungszweck[:120])}</div></td>'
                f'<td class="aktionen-zelle">{zuordnen} '
                f'<button class="klein btn-secondary" hx-post="/api/konto/{k.id}/buchung-anlegen" hx-target="#main" title="Buchung ohne Beleg anlegen (Beleg nachreichen)">Buchung anlegen</button> '
                f'<button class="klein btn-ghost" hx-post="/api/konto/{k.id}/ignorieren" hx-target="#main" title="privat / nicht betrieblich">ignorieren</button></td></tr>')

    ohne_beleg_html = f"""<p class="muted erkl">Kontobewegungen ohne zugeordnete Buchung – die wichtigste Arbeitsliste. Beleg suchen und importieren, dann matcht es automatisch.</p>
  <div class="scroll"><table class="tabelle kompakt"><thead><tr><th>Datum</th><th>Betrag</th><th>Gegenkonto / Zweck</th><th>Aktion</th></tr></thead><tbody>{"".join(konto_zeile(k) for k in op["ohne_beleg"])}</tbody></table></div>"""

    mail_html = f"""<p class="muted erkl">Mails, die nur einen Link zur Rechnung enthalten. Kein Login-Automatismus – Link öffnen, PDF laden, importieren.</p>
  <div class="scroll"><table class="tabelle kompakt"><thead><tr><th>Datum</th><th>Absender</th><th>Betreff</th><th>Link</th><th></th></tr></thead><tbody>{"".join(
        f'<tr><td>{d(m.datum.date()) if m.datum else ""}</td><td>{h(m.absender)}</td><td>{h(m.betreff[:80])}</td><td>{_mail_link(m)}</td>'
        f'<td><button class="klein btn-secondary" hx-post="/api/mailfund/{m.id}/erledigt" hx-target="#main">erledigt</button> <button class="klein btn-ghost" hx-post="/api/mailfund/{m.id}/ignoriert" hx-target="#main">ignorieren</button></td></tr>'
        for m in funde)}</tbody></table></div>"""

    ohne_konto_zeilen = "".join(
        f'<tr><td><input type="checkbox" name="ids" value="{b.id}"></td><td>{d(b.datum)}</td><td class="num">{eur_fmt(b.betrag_brutto)}</td>'
        f'<td>{h(b.lieferant)} <span class="muted klein">{h(b.beschreibung[:60])}</span></td>'
        f'<td>{h(kategorien[b.kategorie_id].name) if b.kategorie_id in kategorien else "–"}</td>'
        f'<td class="aktionen-zelle"><a href="#" class="btn-ghost" hx-get="/ui/pruefen/{b.id}" hx-target="#main" title="Beleg korrigieren">{ICON["stift"]}Korrigieren</a> '
        f'<button class="klein btn-secondary" hx-post="/api/ohnekonto/aktion" hx-vals=\'{{"aktion":"privat","ids":"{b.id}"}}\' hx-target="#main" title="bar oder privat bezahlt – braucht keine Kontobewegung">Privat verauslagt</button> '
        f'<button class="klein btn-ghost" hx-post="/api/ohnekonto/aktion" hx-vals=\'{{"aktion":"stornieren","ids":"{b.id}"}}\' hx-target="#main" hx-confirm="{"Bestätigte Buchung stornieren? Sie bleibt im Journal, zählt aber nicht mehr." if b.status == "bestaetigt" else "Unbestätigten Vorschlag löschen?"}">{"Stornieren" if b.status == "bestaetigt" else "Löschen"}</button></td></tr>'
        for b in op["ohne_konto"][:200])
    ohne_konto_html = f"""<p class="muted erkl">Bar bezahlt, privat verauslagt oder Kontoauszug fehlt noch. Bestätigte Buchungen werden nie gelöscht, nur storniert.</p>
  <form class="auswahl-form" hx-post="/api/ohnekonto/aktion" hx-target="#main">
    {'<p class="muted klein hinweis-rueckfrage">Betrag passt, Datum liegt außerhalb der ±5 Tage. In der Auswahlliste steht die Rechnung mit dem nächsten Datum oben. Alle anhaken und „Rückfragen zuordnen“ übernimmt genau diese.</p>' if filter == "rueckfrage" else ''}
    <div class="auswahl-leiste" hidden><span class="anzahl"></span>
      <button type="submit" name="aktion" value="privat" class="btn-secondary klein">Privat verauslagt</button>
      <button type="submit" name="aktion" value="stornieren" class="btn-ghost klein" hx-confirm="Ausgewählte stornieren (bestätigte) bzw. löschen (Vorschläge)?">Stornieren / Löschen</button></div>
    <div class="scroll"><table class="tabelle kompakt"><thead><tr><th><input type="checkbox" class="alle" title="Alle auswählen"></th><th>Datum</th><th>Brutto</th><th>Lieferant</th><th>Kategorie</th><th>Aktion</th></tr></thead><tbody>{ohne_konto_zeilen}</tbody></table></div>
  </form>"""

    doppel_zeilen = "".join(
        f'<tr><td><input type="checkbox" name="paare" value="{min(a.id, b.id)}-{max(a.id, b.id)}"></td><td>{d(a.datum)} / {d(b.datum)}</td><td class="num">{eur_fmt(a.betrag_brutto)}</td>'
        f'<td>{h(a.lieferant)} – {h(a.rechnungsnummer or "ohne Nr.")} <span class="muted klein">#{min(a.id, b.id)} · #{max(a.id, b.id)}</span></td>'
        f'<td class="aktionen-zelle"><button class="klein btn-primary" hx-post="/api/doppel/zusammenfuehren" hx-vals=\'{{"paare":"{min(a.id, b.id)}-{max(a.id, b.id)}"}}\' hx-target="#main" hx-confirm="Zusammenführen? #{max(a.id, b.id)} geht in #{min(a.id, b.id)} auf, das steht im Belegjournal.">Zusammenführen</button> '
        f'<button class="klein btn-ghost" hx-post="/api/doppel/unterschiedlich" hx-vals=\'{{"paare":"{min(a.id, b.id)}-{max(a.id, b.id)}"}}\' hx-target="#main">Sind unterschiedlich</button></td></tr>'
        for a, b in op["doppel"])
    doppel_html = f"""<p class="muted erkl">Gleicher Betrag und gleiche Rechnungsnummer oder gleicher Lieferant innerhalb von drei Tagen.</p>
  <form class="auswahl-form" hx-target="#main">
    {'<p class="muted klein hinweis-rueckfrage">Betrag passt, Datum liegt außerhalb der ±5 Tage. In der Auswahlliste steht die Rechnung mit dem nächsten Datum oben. Alle anhaken und „Rückfragen zuordnen“ übernimmt genau diese.</p>' if filter == "rueckfrage" else ''}
    <div class="auswahl-leiste" hidden><span class="anzahl"></span>
      <button type="button" class="btn-primary klein" hx-post="/api/doppel/zusammenfuehren" hx-include="closest form" hx-confirm="Ausgewählte Paare zusammenführen? Die ältere Buchung bleibt jeweils.">Zusammenführen</button>
      <button type="button" class="btn-ghost klein" hx-post="/api/doppel/unterschiedlich" hx-include="closest form">Sind unterschiedlich</button></div>
    <div class="scroll"><table class="tabelle kompakt"><thead><tr><th><input type="checkbox" class="alle" title="Alle auswählen"></th><th>Daten</th><th>Betrag</th><th>Lieferant / Nr.</th><th>Aktion</th></tr></thead><tbody>{doppel_zeilen}</tbody></table></div>
  </form>"""

    return f"""
<section class="offen">
  <div class="row zwischen"><p class="muted erkl">Vier Listen, die zusammen sagen, was noch fehlt.</p><button class="btn-secondary" hx-post="/api/matching" hx-target="#main">Matching erneut laufen lassen</button></div>
  {_sektion("Beleg fehlt", len(op["ohne_beleg"]), "Alle Kontobewegungen haben einen Beleg.", ohne_beleg_html, "low")}
  {_sektion("Rechnung manuell laden", len(funde), "Keine Mails mit Rechnungslink gefunden.", mail_html)}
  {_sektion("Beleg ohne Kontobewegung", len(op["ohne_konto"]), "Jede Buchung hat eine Kontobewegung oder ist als privat verauslagt markiert.", ohne_konto_html)}
  {_sektion("Mögliche Doppelbuchungen", len(op["doppel"]), "Keine Auffälligkeiten.", doppel_html, "low")}
</section>
<script>
(function(){{
  document.querySelectorAll('.auswahl-form').forEach(f => {{
    const leiste = f.querySelector('.auswahl-leiste'), alle = f.querySelector('input.alle');
    const boxen = () => [...f.querySelectorAll('tbody input[type=checkbox]')];
    function zaehlen(){{ const n = boxen().filter(b => b.checked).length; leiste.hidden = !n; leiste.querySelector('.anzahl').textContent = n + ' ausgewählt ·'; }}
    if (alle) alle.addEventListener('change', () => {{ boxen().filter(b => !b.closest('tr').hidden).forEach(b => b.checked = alle.checked); zaehlen(); }});
    f.addEventListener('change', e => {{ if (e.target.type === 'checkbox' && e.target !== alle) zaehlen(); }});
    // Suche innerhalb der Liste
    const suche = f.querySelector('.listen-suche'), zaehler = f.querySelector('.listen-zaehler'), tbody = f.querySelector('tbody');
    const zeilen = () => [...tbody.querySelectorAll('tr[data-datum]')];
    function filtern(){{
      const q = (suche.value || '').trim().toLowerCase(); let n = 0;
      zeilen().forEach(tr => {{ const ok = !q || tr.textContent.toLowerCase().includes(q); tr.hidden = !ok; if (ok) n++; }});
      zaehler.textContent = q ? n + ' von ' + zeilen().length : '';
    }}
    if (suche) suche.addEventListener('input', filtern);
    // Sortieren per Klick auf Datum/Betrag
    let sortKey = null, sortDir = -1;
    f.querySelectorAll('th.sortierbar').forEach(th => th.addEventListener('click', () => {{
      const key = th.dataset.sort; sortDir = (sortKey === key) ? -sortDir : (key === 'datum' ? -1 : 1); sortKey = key;
      const rows = zeilen(); rows.sort((a, b) => {{ const va = a.dataset[key], vb = b.dataset[key]; const r = key === 'betrag' ? (+va - +vb) : (va < vb ? -1 : va > vb ? 1 : 0); return r * sortDir; }});
      rows.forEach(r => tbody.appendChild(r));
      f.querySelectorAll('th.sortierbar').forEach(t => {{ t.classList.toggle('aktiv', t === th); t.querySelector('.pfeil').textContent = t === th ? (sortDir > 0 ? '▲' : '▼') : ''; }});
    }}));
  }});
}})();
</script>"""


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
        betrag = summen.get(fr["kategorie"], 0.0)
        bloecke.append(f"""
<details class="frage {"erledigt" if st.get("erledigt") else ""}">
  <summary>
    <label class="check" onclick="event.stopPropagation()"><input type="checkbox" hx-post="/api/fragebogen/{jahr}/{fr["key"]}/toggle" hx-target="#main" {"checked" if st.get("erledigt") else ""}></label>
    <span class="fragetext">{h(fr["frage"])}</span>
    <span class="rechts"><span class="muted klein">{h(kat.name) if kat else ""}</span> <span class="num {"muted" if betrag < 0.005 else ""}">{eur_fmt(betrag) if betrag >= 0.005 else "–"}</span> <span class="btn-ghost klein">Ausgabe erfassen</span></span>
  </summary>
  <form class="row inline erfassen" hx-post="/api/buchung/neu" hx-target="#main">
    <input type="hidden" name="kategorie_id" value="{kat.id if kat else ""}"><input type="hidden" name="richtung" value="ausgabe"><input type="hidden" name="zurueck" value="jahresabschluss:{jahr}">
    <input type="hidden" name="ust_satz" value="{0 if sf in ("fahrtkosten", "homeoffice") else cfg["regelsteuersatz"]}">
    <input type="date" name="datum" placeholder="Zahlungsdatum" min="{jahr}-01-01" max="{jahr}-12-31" required title="Datum der Zahlung (Abflussprinzip)">
    <input name="lieferant" placeholder="Anbieter">
    <input name="beschreibung" placeholder="Beschreibung" size="24">
    <input type="number" step="0.01" name="betrag_brutto" placeholder="Brutto €" style="width:8em" {"" if sf in ("fahrtkosten", "homeoffice") else "required"}>
    {extra}
    <button class="klein btn-secondary">Erfassen</button>
  </form>
</details>""")
    erledigt = sum(1 for f in fragen if status.get(f["key"], {}).get("erledigt"))
    fertig = erledigt == len(fragen)
    prozent = 100 * erledigt // max(1, len(fragen))
    return f"""
<section class="jahresabschluss">
  <div class="fortschritt-leiste">
    <div class="row zwischen"><span><strong>{erledigt}/{len(fragen)}</strong> <span class="muted">Fragen geprüft</span></span>
    <span class="badge {"ok" if fertig else ""}">{"vollständig" if fertig else "offen"}</span></div>
    <div class="balken"><div class="fuellung" style="width:{prozent}%"></div></div>
  </div>
  <p class="muted erkl">Typische vergessene Posten. Haken setzen, wenn geprüft – auch wenn es nichts zu erfassen gab. Datum ist das Zahlungsdatum (Abflussprinzip).</p>
  {''.join(bloecke)}
  <div class="row aktionen"><a class="button btn-primary" href="#" hx-get="/ui/export?jahr={jahr}" hx-target="#main">Jahresabschluss abschließen → Exporte für Elster</a></div>
</section>"""


# --------------------------------------------------------------- Export

def export_view(jahr: int, eur: list[dict], ustva_liste: list[dict], jahre: list[int]) -> str:
    def zeile(z: dict) -> str:
        summe = z["zeile"] is None
        gewinn = z["bezeichnung"].startswith("Gewinn")
        cls = ("summe " if summe else "") + ("fett " if gewinn else "")
        wert_cls = ("plus" if z["betrag"] >= 0 else "minus") if gewinn else ""
        name = f'<span class="muted">{z["zeile"]} ·</span> {h(z["bezeichnung"])}' if not summe else h(z["bezeichnung"])
        return f'<tr class="{cls.strip()}"><td>{name}</td>{eur_zelle(z["betrag"], wert_cls)}</tr>'
    eur_html = "".join(zeile(z) for z in eur)
    ustva_html = ""
    for u in ustva_liste:
        if not u["positionen"]:
            ustva_html += f'<div class="karte"><h4>Q{u["quartal"]}</h4><p class="muted">Keine §13b-Positionen.</p></div>'
            continue
        kz = "".join(f'<tr><td>Kz {h(k)}</td>{eur_zelle(v)}</tr>' for k, v in u["kennzahlen"].items())
        pos = "".join(f'<li>{d(p["buchung"].datum)} {h(p["buchung"].lieferant)} netto {eur_fmt(p["buchung"].betrag_netto)} → Kz {p["kz_basis"]}/{p["kz_steuer"]}: {eur_fmt(p["steuer"])}</li>' for p in u["positionen"])
        ustva_html += f'<div class="karte"><h4>Q{u["quartal"]} · Zahllast {eur_fmt(u["zahllast"])}</h4><table class="tabelle kompakt">{kz}</table><ul class="klein">{pos}</ul></div>'
    return f"""
<section>
  <p class="muted erkl">Kein Elster-Direktversand – die Zahlen werden von Hand eingetragen. Nur bestätigte, nicht stornierte Buchungen fließen ein.</p>

  <h3>Anlage EÜR {jahr}</h3>
  <table class="tabelle kompakt eur-tabelle"><thead><tr><th>Zeile · Bezeichnung</th><th class="num">Betrag</th></tr></thead><tbody>{eur_html}</tbody></table>
  <div class="row"><a class="button btn-secondary" href="/export/eur.csv?jahr={jahr}">CSV</a> <a class="button btn-secondary" href="/export/eur.pdf?jahr={jahr}" target="_blank">PDF</a> <a class="button btn-secondary" href="/export/eur.json?jahr={jahr}">JSON</a></div>

  <h3>UStVA je Quartal – nur §13b</h3>
  <p class="muted erkl">Als Kleinunternehmer entsteht eine UStVA-Pflicht nur für bezogene Leistungen mit Umkehr der Steuerschuld. Kz 46/47 (EU) bzw. 84/85 (Drittland). Einmalig fachlich prüfen lassen.</p>
  <div class="karten">{ustva_html}</div>

  <h3>Weitere Ausgaben</h3>
  <div class="row">
    <a class="button btn-secondary" href="/export/quartale.csv?jahr={jahr}&modus=brutto">Quartalstabelle CSV</a>
    <a class="button btn-secondary" href="/export/quartale.pdf?jahr={jahr}&modus=brutto" target="_blank">Quartalstabelle PDF</a>
    <a class="button btn-secondary" href="/export/belegjournal.csv?jahr={jahr}">Belegjournal CSV</a>
  </div>
</section>"""


# --------------------------------------------------------- Einstellungen

def einstellungen_view(ollama_status: dict, mail: dict, hat_pw: bool, regeln: list[Regel], kategorien: dict[int, Kategorie],
                       pfade: dict, meldung: str = "", meldung_typ: str = "ok-box") -> str:
    regeln_html = "".join(
        f'<tr><td><code>{h(r.muster)}</code>{" <span class=muted>(regex)</span>" if r.ist_regex else ""}</td><td>{h(kategorien[r.kategorie_id].name) if r.kategorie_id in kategorien else "?"}</td>'
        f'<td>{r.prioritaet}</td><td>{"aus Korrektur" if r.erstellt_aus_korrektur else "manuell"}</td><td>{r.treffer}</td>'
        f'<td><button class="klein gefahr" hx-post="/api/regel/{r.id}/loeschen" hx-target="#main">löschen</button></td></tr>' for r in regeln)
    kat_opts = "".join(f'<option value="{k.id}">{h(k.name)}</option>' for k in sorted(kategorien.values(), key=lambda k: k.name))
    imap, emlx = mail["imap"], mail["emlx"]
    return f"""
<section>
  {meldung_box(meldung, meldung_typ) if meldung else ''}
  <div class="karte"><h3>Dateien</h3>
    <p class="muted klein">Version <code>{h(pfade.get("version", "dev"))}</code> · Programmordner <code>{h(str(__import__("app.config", fromlist=["APP_DIR"]).APP_DIR.parent))}</code></p>
    <p>Datenbank: <code>{h(pfade["db"])}</code><br>Belegordner: <code>{h(pfade["belege"])}</code><br>Regeln &amp; Grenzwerte: <code>{h(pfade["regeln"])}</code>
    <button class="klein" hx-post="/api/config/reload" hx-target="#main">neu laden</button></p>
    <p class="muted">Sichern heißt: diese drei Dinge kopieren. Kein Cloud-Sync durch das Tool.</p>
    <div class="row"><button class="gefahr" hx-post="/api/beenden" hx-target="#main" hx-confirm="Steuerfuchs beenden? Der Server wird gestoppt; alle Daten sind gespeichert.">Steuerfuchs beenden</button></div></div>

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
    """cls: ok-box (Erfolg), warn-box (Hinweis), fehler-box (Fehler). Icon kommt per CSS."""
    return f'<p class="{cls}" role="{"alert" if cls == "fehler-box" else "status"}"><span>{h(text)}</span></p>'


# ------------------------------------------------------------ Auswertung

def auswertung_view(jahr: int, jahre: list[int]) -> str:
    jahr_opts = "".join(f'<option value="{j}" {"selected" if j == jahr else ""}>{j}</option>' for j in jahre)
    formen = (("saeulen", "Quartale"), ("monate", "Monate"), ("linie", "Gewinnverlauf"), ("balken", "Kategorien"),
              ("donut", "Anteile"), ("tabelle", "Tabelle"))
    knoepfe = "".join(f'<button type="button" data-form="{f}" class="{"aktiv" if f == "saeulen" else ""}">{n}</button>' for f, n in formen)
    return f"""
<section id="auswertung" data-jahr="{jahr}">
  <div class="row zwischen">
    <p class="muted erkl" id="chart-erkl">Einnahmen und abzugsfähige Ausgaben je Quartal. Nur bestätigte Buchungen.</p>
    <div class="tabs" id="chart-formen">{knoepfe}</div>
  </div>
  <p class="muted" id="chart-erkl-alt" hidden>Einnahmen und abzugsfähige Ausgaben je Quartal. Nur bestätigte Buchungen; Grün = Plus, Gelb = neutral, Rot = Minus.</p>
  <div class="karte chart-karte">
    <div class="legende" id="chart-legende"></div>
    <div class="chart-wrap" id="chart-wrap"><svg id="chart" viewBox="0 0 960 380" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Diagramm"></svg><div class="tooltip" id="chart-tip" hidden></div><div id="chart-tabelle" hidden></div></div>
  </div>
</section>
<script>
(function(){{
  const wurzel = document.getElementById('auswertung'); if (!wurzel) return;
  const jahr = wurzel.dataset.jahr, svg = document.getElementById('chart'), tip = document.getElementById('chart-tip');
  const legende = document.getElementById('chart-legende'), tabelle = document.getElementById('chart-tabelle'), wrap = document.getElementById('chart-wrap');
  const erkl = document.getElementById('chart-erkl');
  const NS = 'http://www.w3.org/2000/svg';
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const dunkel = () => document.documentElement.dataset.theme !== 'light';
  const KAT = () => dunkel() ? ['#3987e5','#d95926','#199e70','#c98500','#d55181','#008300','#9085e9'] : ['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#4a3aa7'];
  const MON = ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
  const eur = x => x.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) + ' €';
  const kurz = x => Math.abs(x) >= 1000 ? (x/1000).toLocaleString('de-DE', {{maximumFractionDigits: 1}}) + ' k' : x.toLocaleString('de-DE', {{maximumFractionDigits: 0}});
  function el(tag, attrs, text){{ const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; return e; }}
  function leer(){{ while (svg.firstChild) svg.removeChild(svg.firstChild); legende.innerHTML = ''; }}
  function ticks(max){{ if (max <= 0) return [0, 1]; const roh = max / 4, p = Math.pow(10, Math.floor(Math.log10(roh))); const s = [1,2,2.5,5,10].map(m => m*p).find(m => m >= roh); const out=[]; for (let v=0; v <= max + s*0.999; v += s) out.push(Math.round(v*100)/100); return out; }}
  function zeigeTip(ev, html){{ tip.innerHTML = html; tip.hidden = false; const r = wrap.getBoundingClientRect(); let x = ev.clientX - r.left + 14, y = ev.clientY - r.top - 10; if (x + 220 > r.width) x -= 240; tip.style.left = x + 'px'; tip.style.top = y + 'px'; }}
  function hideTip(){{ tip.hidden = true; }}
  function legendeSetzen(eintraege){{ legende.innerHTML = eintraege.map(e => `<span><i style="background:${{e.farbe}}"></i>${{e.name}}${{e.wert != null ? ' <b>' + e.wert + '</b>' : ''}}</span>`).join(''); }}
  function saeule(x, y0, y1, breite, farbe, r){{ const h = Math.max(0, y0 - y1); if (h < 0.5) return el('rect', {{x, y: y0 - 1, width: breite, height: 1, fill: farbe, opacity: .35}}); const rr = Math.min(r, h, breite/2); return el('path', {{d: `M${{x}} ${{y0}} V${{y1+rr}} a${{rr}} ${{rr}} 0 0 1 ${{rr}} -${{rr}} H${{x+breite-rr}} a${{rr}} ${{rr}} 0 0 1 ${{rr}} ${{rr}} V${{y0}} Z`, fill: farbe}}); }}
  function balkenH(x0, x1, y, hoehe, farbe, r){{ const w = Math.max(0, x1 - x0); if (w < 0.5) return el('rect', {{x: x0, y, width: 1, height: hoehe, fill: farbe, opacity: .35}}); const rr = Math.min(r, w, hoehe/2); return el('path', {{d: `M${{x0}} ${{y}} H${{x1-rr}} a${{rr}} ${{rr}} 0 0 1 ${{rr}} ${{rr}} V${{y+hoehe-rr}} a${{rr}} ${{rr}} 0 0 1 -${{rr}} ${{rr}} H${{x0}} Z`, fill: farbe}}); }}
  function achsen(L, R, T, B, tk, max){{
    tk.forEach(v => {{ const y = B - (B - T) * v / max; svg.appendChild(el('line', {{x1: L, x2: R, y1: y, y2: y, class: 'grid'}})); svg.appendChild(el('text', {{x: L - 8, y: y + 4, class: 'tick', 'text-anchor': 'end'}}, kurz(v))); }});
  }}

  function gruppen(d, labels, reihen, hinweis){{
    // reihen: [{{name, farbe, werte[]}}] – Säulen je Gruppe, 2px Luft, ≤24px dick
    const L = 70, R = 940, T = 20, B = 330, n = labels.length;
    const max = Math.max(1, ...reihen.flatMap(r => r.werte)); const tk = ticks(max); const mx = tk[tk.length - 1];
    achsen(L, R, T, B, tk, mx);
    svg.appendChild(el('line', {{x1: L, x2: R, y1: B, y2: B, class: 'achse'}}));
    const band = (R - L) / n, dick = Math.min(24, (band * 0.6 - 2 * (reihen.length - 1)) / reihen.length);
    labels.forEach((lab, i) => {{
      const cx = L + band * (i + 0.5); svg.appendChild(el('text', {{x: cx, y: B + 20, class: 'tick', 'text-anchor': 'middle'}}, lab));
      const gesamt = dick * reihen.length + 2 * (reihen.length - 1);
      reihen.forEach((r, j) => {{
        const x = cx - gesamt / 2 + j * (dick + 2), y1 = B - (B - T) * r.werte[i] / mx;
        svg.appendChild(saeule(x, B, y1, dick, r.farbe, 4));
      }});
      const hit = el('rect', {{x: L + band * i, y: T, width: band, height: B - T, fill: 'transparent', 'data-i': i}});
      hit.addEventListener('mousemove', ev => {{ const k = +ev.currentTarget.dataset.i; zeigeTip(ev, `<b>${{labels[k]}}</b><br>${{reihen.map(q => `<i style="background:${{q.farbe}}"></i>${{q.name}}: ${{eur(q.werte[k])}}`).join('<br>')}}`); }});
      hit.addEventListener('mouseleave', hideTip); svg.appendChild(hit);
    }});
    legendeSetzen(reihen.map(r => ({{name: r.name, farbe: r.farbe, wert: eur(r.werte.reduce((a, b) => a + b, 0))}})));
    erkl.textContent = hinweis;
  }}

  function linie(d){{
    const L = 70, R = 900, T = 30, B = 330, m = d.monate, w = m.map(z => z.gewinn_kumuliert);
    const lo = Math.min(0, ...w), hi = Math.max(0, ...w);
    const basis = ticks(Math.max(hi, -lo, 1)), schritt = basis[1] - basis[0];   // ein Schritt für beide Seiten
    const mnLo = Math.floor(lo / schritt) * schritt, mxHi = Math.ceil(hi / schritt) * schritt || schritt;
    const tk = []; for (let v = mnLo; v <= mxHi + schritt * 0.001; v += schritt) tk.push(Math.round(v * 100) / 100);
    const y = v => B - (B - T) * (v - mnLo) / (mxHi - mnLo || 1);
    tk.forEach(v => {{ svg.appendChild(el('line', {{x1: L, x2: R, y1: y(v), y2: y(v), class: v === 0 ? 'achse' : 'grid'}})); svg.appendChild(el('text', {{x: L - 8, y: y(v) + 4, class: 'tick', 'text-anchor': 'end'}}, kurz(v))); }});
    const x = i => L + (R - L) * i / 11;
    // Farbverlauf wie ein Kurschart: unten (Verlust) rot, an der Nulllinie orange, oben grün
    const defs = el('defs', {{}}); const nullAnteil = Math.min(1, Math.max(0, (y(0) - T) / (B - T)));
    const grad = el('linearGradient', {{id: 'gewinn-grad', gradientUnits: 'userSpaceOnUse', x1: 0, x2: 0, y1: T, y2: B}});
    grad.appendChild(el('stop', {{offset: '0%', 'stop-color': css('--gruen')}}));
    grad.appendChild(el('stop', {{offset: (Math.max(0.05, nullAnteil - 0.05) * 100) + '%', 'stop-color': css('--orange')}}));
    grad.appendChild(el('stop', {{offset: (Math.min(1, nullAnteil + 0.15) * 100) + '%', 'stop-color': css('--rot')}}));
    grad.appendChild(el('stop', {{offset: '100%', 'stop-color': css('--rot')}}));
    defs.appendChild(grad); svg.appendChild(defs);
    const farbe = 'url(#gewinn-grad)';
    const pfad = w.map((v, i) => (i ? 'L' : 'M') + x(i) + ' ' + y(v)).join(' ');
    svg.appendChild(el('path', {{d: pfad + ` L${{x(11)}} ${{y(0)}} L${{x(0)}} ${{y(0)}} Z`, fill: farbe, opacity: .16}}));
    svg.appendChild(el('path', {{d: pfad, fill: 'none', stroke: farbe, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}}));
    m.forEach((z, i) => {{
      svg.appendChild(el('text', {{x: x(i), y: B + 20, class: 'tick', 'text-anchor': 'middle'}}, MON[i]));
      const c = el('circle', {{cx: x(i), cy: y(w[i]), r: 4.5, fill: w[i] > 0 ? css('--gruen') : (w[i] < 0 ? css('--rot') : css('--orange')), stroke: css('--card'), 'stroke-width': 2}}); svg.appendChild(c);
      const hit = el('rect', {{x: x(i) - (R - L) / 22, y: T, width: (R - L) / 11, height: B - T, fill: 'transparent'}});
      hit.addEventListener('mousemove', ev => zeigeTip(ev, `<b>${{MON[i]}} ${{jahr}}</b><br>Einnahmen: ${{eur(z.einnahmen)}}<br>Ausgaben: ${{eur(z.ausgaben)}}<br>Gewinn kumuliert: ${{eur(z.gewinn_kumuliert)}}`));
      hit.addEventListener('mouseleave', hideTip); svg.appendChild(hit);
    }});
    const ende = w[11]; const t = el('text', {{x: x(11) + 10, y: y(ende) + 4, class: 'wert'}}, eur(ende)); svg.appendChild(t);
    legendeSetzen([{{name: 'Gewinn kumuliert', farbe: ende >= 0 ? css('--gruen') : css('--rot'), wert: eur(ende)}}]);
    erkl.textContent = 'Kumulierter Gewinn über das Jahr (Einnahmen minus abzugsfähige Ausgaben, AfA gleichmäßig verteilt). Nulllinie hervorgehoben.';
  }}

  function balken(d){{
    const kats = d.kategorien.filter(k => k.richtung === 'ausgabe' && k.abzugsfaehig > 0).sort((a, b) => b.abzugsfaehig - a.abzugsfaehig).slice(0, 12);
    if (!kats.length) return leerHinweis();
    const L = 240, R = 880, T = 24, schritt = Math.min(56, (330 - T) / kats.length), hoehe = Math.min(24, schritt - 8);
    const max = Math.max(...kats.map(k => k.abzugsfaehig)); const farbe = css('--orange');
    kats.forEach((k, i) => {{
      const y = T + schritt * i + (schritt - hoehe) / 2, x1 = L + (R - L) * k.abzugsfaehig / max;
      svg.appendChild(el('text', {{x: L - 10, y: y + hoehe / 2 + 4, class: 'tick', 'text-anchor': 'end'}}, k.name.length > 30 ? k.name.slice(0, 29) + '…' : k.name));
      const b = balkenH(L, x1, y, hoehe, farbe, 4); svg.appendChild(b);
      svg.appendChild(el('text', {{x: x1 + 8, y: y + hoehe / 2 + 4, class: 'wert'}}, eur(k.abzugsfaehig)));
      const hit = el('rect', {{x: 0, y: y - 3, width: 960, height: hoehe + 6, fill: 'transparent'}});
      hit.addEventListener('mousemove', ev => zeigeTip(ev, `<b>${{k.name}}</b><br>abzugsfähig: ${{eur(k.abzugsfaehig)}}<br>brutto: ${{eur(k.brutto)}}<br>USt enthalten: ${{eur(k.ust)}}<br>${{k.anzahl}} Buchungen`));
      hit.addEventListener('mouseleave', hideTip); svg.appendChild(hit);
    }});
    legendeSetzen([]);
    erkl.textContent = 'Abzugsfähige Ausgaben je Kategorie, absteigend.';
  }}

  function ring(cx, cy, r, ri, farbe, a1, a2){{
    // Ein voller Kreis (360°) ist als ein Bogen unsichtbar – deshalb ab 359,9° in zwei Hälften zeichnen
    if (a2 - a1 >= 2 * Math.PI - 0.001) {{ const g = el('g', {{}}); g.appendChild(ring(cx, cy, r, ri, farbe, a1, a1 + Math.PI)); g.appendChild(ring(cx, cy, r, ri, farbe, a1 + Math.PI, a2)); return g; }}
    const gross = (a2 - a1) > Math.PI ? 1 : 0, p = (rad, w) => [cx + rad * Math.cos(w), cy + rad * Math.sin(w)];
    const [x1, y1] = p(r, a1), [x2, y2] = p(r, a2), [x3, y3] = p(ri, a2), [x4, y4] = p(ri, a1);
    return el('path', {{d: `M${{x1}} ${{y1}} A${{r}} ${{r}} 0 ${{gross}} 1 ${{x2}} ${{y2}} L${{x3}} ${{y3}} A${{ri}} ${{ri}} 0 ${{gross}} 0 ${{x4}} ${{y4}} Z`, fill: farbe, stroke: css('--card'), 'stroke-width': 2}});
  }}
  function donutZeichnen(eintraege, cx, cy, r, ri, legendeX, titel){{
    // eintraege: [{{name, wert}}] – mehr als sechs werden zu „Sonstige“
    let e = eintraege.filter(k => k.wert > 0).sort((a, b) => b.wert - a.wert);
    const farben = KAT();
    if (!e.length) {{ svg.appendChild(el('text', {{x: cx, y: cy, class: 'tick', 'text-anchor': 'middle'}}, 'keine Daten')); svg.appendChild(el('text', {{x: cx, y: cy - r - 14, class: 'label', 'text-anchor': 'middle'}}, titel)); return; }}
    if (e.length > 6) {{ const rest = e.slice(5).reduce((a, k) => a + k.wert, 0); e = e.slice(0, 5).concat([{{name: 'Sonstige (' + (eintraege.length - 5) + ')', wert: rest}}]); }}
    const gesamt = e.reduce((a, k) => a + k.wert, 0); let winkel = -Math.PI / 2;
    e.forEach((k, i) => {{
      const a2 = winkel + k.wert / gesamt * 2 * Math.PI; const seg = ring(cx, cy, r, ri, farben[i], winkel, a2);
      seg.addEventListener('mousemove', ev => zeigeTip(ev, `<b>${{k.name}}</b><br>${{eur(k.wert)}} · ${{(k.wert / gesamt * 100).toFixed(1)}} %`));
      seg.addEventListener('mouseleave', hideTip); svg.appendChild(seg); winkel = a2;
    }});
    svg.appendChild(el('text', {{x: cx, y: cy - 4, class: 'hero', 'text-anchor': 'middle'}}, kurz(gesamt) + (Math.abs(gesamt) >= 1000 ? '' : ' €')));
    svg.appendChild(el('text', {{x: cx, y: cy + 16, class: 'tick', 'text-anchor': 'middle'}}, titel));
    e.forEach((k, i) => {{
      const y = cy - r + 10 + i * 36; svg.appendChild(el('rect', {{x: legendeX, y: y - 11, width: 12, height: 12, rx: 3, fill: farben[i]}}));
      svg.appendChild(el('text', {{x: legendeX + 20, y, class: 'label', style: 'font-size:12.5px'}}, k.name.length > 24 ? k.name.slice(0, 23) + '…' : k.name));
      svg.appendChild(el('text', {{x: legendeX + 20, y: y + 15, class: 'tick'}}, `${{eur(k.wert)}} · ${{(k.wert / gesamt * 100).toFixed(1)}} %`));
    }});
  }}
  function donut(d){{
    const ausgaben = d.kategorien.filter(k => k.richtung === 'ausgabe').map(k => ({{name: k.name, wert: k.abzugsfaehig}}));
    const kunden = (d.kunden || []).map(k => ({{name: k.name, wert: k.betrag}}));
    if (!ausgaben.some(k => k.wert > 0) && !kunden.some(k => k.wert > 0)) return leerHinweis();
    donutZeichnen(kunden, 130, 190, 105, 68, 255, 'Umsatz nach Kunde');
    donutZeichnen(ausgaben, 610, 190, 105, 68, 735, 'Ausgaben nach Kategorie');
    svg.appendChild(el('line', {{x1: 480, x2: 480, y1: 40, y2: 340, class: 'grid'}}));
    legendeSetzen([]);
    erkl.textContent = 'Links: Wer bringt welchen Anteil vom Umsatz. Rechts: Wohin gehen die abzugsfähigen Ausgaben. Mehr als sechs Positionen werden zu „Sonstige“ zusammengefasst.';
  }}

  function tabelleZeigen(d){{
    const q = d.quartale.map(z => `<tr><td>Q${{z.q}}</td><td class="num plus">${{eur(z.einnahmen)}}</td><td class="num minus">${{eur(z.ausgaben)}}</td><td class="num ${{z.gewinn >= 0 ? 'plus' : 'minus'}}">${{eur(z.gewinn)}}</td><td class="num neutral">${{eur(z.ust)}}</td></tr>`).join('');
    const m = d.monate.map((z, i) => `<tr><td>${{MON[i]}}</td><td class="num plus">${{eur(z.einnahmen)}}</td><td class="num minus">${{eur(z.ausgaben)}}</td><td class="num ${{z.gewinn_kumuliert >= 0 ? 'plus' : 'minus'}}">${{eur(z.gewinn_kumuliert)}}</td><td class="num neutral">${{eur(z.ust)}}</td></tr>`).join('');
    tabelle.innerHTML = `<div class="karten"><div><h4>Quartale</h4><table class="tabelle kompakt"><thead><tr><th></th><th>Einnahmen</th><th>Ausgaben</th><th>Gewinn</th><th>Entg. Vorsteuer</th></tr></thead><tbody>${{q}}</tbody></table></div>
      <div><h4>Monate</h4><table class="tabelle kompakt"><thead><tr><th></th><th>Einnahmen</th><th>Ausgaben</th><th>Gewinn kum.</th><th>Entg. Vorsteuer</th></tr></thead><tbody>${{m}}</tbody></table></div></div>`;
    erkl.textContent = 'Dieselben Zahlen als Tabelle – für Screenreader, Kopieren und Gegenrechnen.';
  }}

  function leerHinweis(){{
    svg.hidden = true; tabelle.hidden = false; legendeSetzen([]);
    tabelle.innerHTML = '<p class="leer-hinweis">Für ' + jahr + ' sind noch keine Buchungen erfasst. <a href="#" hx-get="/ui/import" hx-target="#main">→ Belege importieren</a></p>';
    htmx.process(tabelle);
  }}
  function tabsDaempfen(d){{
    const kats = d.kategorien.filter(k => k.richtung === 'ausgabe' && k.abzugsfaehig > 0).length;
    const leer = {{saeulen: d.jahr_summe.einnahmen === 0 && d.jahr_summe.ausgaben === 0, monate: d.jahr_summe.einnahmen === 0 && d.jahr_summe.ausgaben === 0,
                  linie: d.monate.every(z => z.gewinn_kumuliert === 0), balken: kats === 0, donut: kats === 0, tabelle: false}};
    document.querySelectorAll('#chart-formen button').forEach(b => b.classList.toggle('leer', !!leer[b.dataset.form]));
  }}

  let daten = null, form = 'saeulen';
  function render(){{
    leer(); hideTip(); const ist = form === 'tabelle'; svg.hidden = ist; tabelle.hidden = !ist; if (!ist) tabelle.innerHTML = ''; if (!daten) return;
    const g = css('--gruen'), r = css('--rot'), y = css('--gelb'), d = daten;
    const ohne = d.jahr_summe.einnahmen === 0 && d.jahr_summe.ausgaben === 0;
    if (ohne && !ist) return leerHinweis();
    if (form === 'saeulen') gruppen(d, d.quartale.map(z => 'Q' + z.q), [{{name: 'Einnahmen', farbe: g, werte: d.quartale.map(z => z.einnahmen)}}, {{name: 'Ausgaben (abzugsfähig)', farbe: r, werte: d.quartale.map(z => z.ausgaben)}}, {{name: 'Entgangene Vorsteuer', farbe: y, werte: d.quartale.map(z => z.ust)}}], 'Einnahmen, abzugsfähige Ausgaben und entgangene Vorsteuer je Quartal. Grün = Plus, Rot = Minus, Gelb = neutral.');
    else if (form === 'monate') gruppen(d, MON, [{{name: 'Einnahmen', farbe: g, werte: d.monate.map(z => z.einnahmen)}}, {{name: 'Ausgaben (abzugsfähig)', farbe: r, werte: d.monate.map(z => z.ausgaben)}}], 'Einnahmen und abzugsfähige Ausgaben je Monat.');
    else if (form === 'linie') linie(d);
    else if (form === 'balken') balken(d);
    else if (form === 'donut') donut(d);
    else tabelleZeigen(d);
  }}
  document.getElementById('chart-formen').addEventListener('click', e => {{ const b = e.target.closest('button'); if (!b) return; form = b.dataset.form; document.querySelectorAll('#chart-formen button').forEach(x => x.classList.toggle('aktiv', x === b)); render(); }});
  document.getElementById('theme-toggle').addEventListener('click', () => setTimeout(render, 30));
  fetch('/api/auswertung?jahr=' + jahr).then(r => r.json()).then(d => {{ daten = d; tabsDaempfen(d); render(); }});
}})();
</script>"""


# ------------------------------------------------------------ Abgleich

def abgleich_view(zeilen: list[dict], regeln: list[IgnorRegel], jahr: int, filter: str, vorschlag: dict[int, str]) -> str:
    z_alle = zeilen
    zaehl = {st: sum(1 for z in z_alle if z["status"] == st) for st in ("zugeordnet", "rueckfrage", "kein_beleg", "ignoriert")}
    doppel = sum(1 for z in z_alle if z["doppelt"])
    if filter == "offen":
        zeilen = [z for z in z_alle if z["status"] in ("rueckfrage", "kein_beleg")]
    elif filter == "ignoriert":
        zeilen = [z for z in z_alle if z["status"] == "ignoriert"]
    elif filter == "zugeordnet":
        zeilen = [z for z in z_alle if z["status"] == "zugeordnet"]
    elif filter == "rueckfrage":
        zeilen = [z for z in z_alle if z["status"] == "rueckfrage"]
    tabs = "".join(
        f'<button type="button" class="{"aktiv" if filter == f else ""}" hx-get="/ui/abgleich?filter={f}" hx-target="#main">{name} <span class="z">{n}</span></button>'
        for f, name, n in (("offen", "Offen", zaehl["rueckfrage"] + zaehl["kein_beleg"]), ("rueckfrage", "Rückfragen", zaehl["rueckfrage"]),
                           ("zugeordnet", "Zugeordnet", zaehl["zugeordnet"]),
                           ("ignoriert", "Ignoriert", zaehl["ignoriert"]), ("alle", "Alle", len(z_alle))))

    def status_zelle(z: dict) -> str:
        k, st = z["k"], z["status"]
        if st == "zugeordnet":
            b = z["buchung"]
            return (f'<span class="badge ok">zugeordnet</span><div class="klein"><a href="#" hx-get="/ui/pruefen/{b.id}" hx-target="#main">{h(b.lieferant or "Buchung")} · {d(b.datum)}</a></div>'
                    if b else '<span class="badge ok">zugeordnet</span>')
        if st == "ignoriert":
            return '<span class="badge">ignoriert</span>'
        if st == "rueckfrage":
            return f'<span class="badge mid">Rückfrage</span><div class="muted klein">Betrag passt zu {len(z["kandidaten"])} Rechnung(en), Datum weicht ab</div>'
        vs = vorschlag.get(k.id, "")
        return '<span class="badge low">kein Beleg</span>' + (f'<div class="muted klein">Regel: {h(vs)}</div>' if vs else '')

    def aktionen(z: dict) -> str:
        k, st = z["k"], z["status"]
        vals = lambda aktion: f'hx-vals=\'{{"aktion":"{aktion}","ids":"{k.id}","jahr":"{jahr}"}}\' hx-post="/api/abgleich/aktion" hx-target="#main"'
        if st == "zugeordnet":
            b = z["buchung"]
            oeffnen = f'<a href="#" class="klein btn-secondary button" hx-get="/ui/pruefen/{b.id}" hx-target="#main">{ICON["oeffnen"]}Beleg öffnen</a> ' if b else ""
            return oeffnen + f'<button class="klein btn-ghost" {vals("loesen")} title="Zuordnung zur Rechnung wieder aufheben">{ICON["unlink"]}Zuordnung lösen</button>'
        if st == "ignoriert":
            return f'<button class="klein btn-ghost" {vals("freigeben")} title="Wieder in die offene Liste aufnehmen">{ICON["undo"]}freigeben</button>'
        if st == "rueckfrage":
            opts = "".join(f'<option value="{b.id}">{d(b.datum)} · {h(b.lieferant)} · {eur_fmt(b.betrag_brutto)}{" · bestätigt" if b.status == "bestaetigt" else ""}</option>' for b in z["kandidaten"])
            return (f'<form class="inline" hx-post="/api/abgleich/{k.id}/zuordnen" hx-target="#main"><input type="hidden" name="jahr" value="{jahr}"><input type="hidden" name="filter" value="{filter}"><select name="buchung_id">{opts}</select> <button class="klein btn-secondary">{ICON["link"]}zuordnen</button></form> '
                    f'<button class="klein btn-ghost" {vals("ignorieren")}>{ICON["auge_zu"]}ignorieren</button>')
        return (f'<form class="inline beleg-upload" hx-post="/api/abgleich/{k.id}/beleg" hx-encoding="multipart/form-data" hx-target="#main" hx-trigger="change"><input type="hidden" name="jahr" value="{jahr}"><input type="hidden" name="filter" value="{filter}">'
                f'<label class="klein btn-secondary button" title="Rechnung zu dieser Buchung hochladen">{ICON["upload"]}Beleg hochladen<input type="file" name="datei" accept=".pdf,.xml,.png,.jpg,.jpeg" hidden></label></form> '
                f'<button class="klein btn-secondary" {vals("anlegen")} title="Buchungsvorschlag ohne Beleg anlegen">{ICON["datei_plus"]}ohne Beleg buchen</button> '
                f'<button class="klein btn-ghost" {vals("ignorieren")}>{ICON["auge_zu"]}ignorieren</button> '
                f'<button class="klein btn-ghost" {vals("regel")} title="Regel: „{h(k.gegenkonto or k.verwendungszweck[:40])}“ künftig immer ignorieren">{ICON["sperren"]}immer ignorieren</button>')

    def status_rang(z: dict) -> int:
        """Sortierreihenfolge der Abgleich-Spalte: erst Rückfragen, dann Dubletten, dann ohne Beleg, dann erledigt."""
        st = z["status"]
        if st == "rueckfrage":
            return 0
        if st == "kein_beleg":
            return 1 if z["doppelt"] else 2
        return 3 if st == "zugeordnet" else 4

    rows = "".join(
        f'<tr class="{"doppelt" if z["doppelt"] else ""}" data-datum="{z["k"].datum.isoformat()}" data-betrag="{z["k"].betrag:.2f}" data-status="{status_rang(z)}"><td><input type="checkbox" name="ids" value="{z["k"].id}"></td>'
        f'<td>{d(z["k"].datum)}</td><td class="num">{eur_fmt(z["k"].betrag)}<div><span class="badge {"plus-b" if z["k"].betrag > 0 else "minus-b"}">{"Einnahme" if z["k"].betrag > 0 else "Ausgabe"}</span></div></td>'
        f'<td class="zweck">{h(z["k"].gegenkonto)}<div class="muted klein">{h(z["k"].verwendungszweck[:140])}</div>'
        + (f'<div class="klein"><span class="badge low">evtl. doppelt</span> <span class="muted">gleicher Betrag und Empfänger am {d(z["doppelt"].datum)} – prüfen, ob beide echt sind</span></div>' if z["doppelt"] else "")
        + f'</td><td>{status_zelle(z)}</td><td class="aktionen-zelle"><div class="aktionen-inline">{aktionen(z)}</div></td></tr>'
        for z in zeilen)
    regeln_html = "".join(f'<li><code>{h(r.muster)}</code> <span class="muted klein">{r.treffer} Treffer</span> '
                          f'<button class="klein btn-ghost" hx-post="/api/ignorregel/{r.id}/loeschen" hx-vals=\'{{"jahr":"{jahr}","filter":"{filter}"}}\' hx-target="#main">entfernen</button></li>' for r in regeln)
    return f"""
<section class="abgleich">
  <p class="muted erkl">Jede Kontobewegung wird mit den importierten Rechnungen verglichen (Betrag exakt, Datum ±5 Tage). Was nicht sicher ist, wird hier nachgefragt. Privates ignorierst du einmal – oder dauerhaft per Regel.</p>
  <div class="karte">
    <form hx-post="/api/konto/import" hx-target="#main" hx-encoding="multipart/form-data" class="row">
      <strong>Kontoauszug einlesen</strong>
      <input type="file" name="datei" accept=".pdf,.csv,.xml,.txt" required>
      <button class="btn-primary">PDF / CSV / CAMT.053 einlesen und abgleichen</button>
      <span class="muted klein">Bereits bekannte Bewegungen werden übersprungen.</span>
    </form>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="l">Zugeordnet</div><div class="w">{zaehl["zugeordnet"]}</div></div>
    <div class="kpi gelb"><div class="l">Rückfragen</div><div class="w">{zaehl["rueckfrage"]}</div></div>
    <div class="kpi"><div class="l">Ohne Beleg</div><div class="w">{zaehl["kein_beleg"]}</div></div>
    <div class="kpi"><div class="l">Ignoriert</div><div class="w">{zaehl["ignoriert"]}</div></div>
    <div class="kpi {"rot" if doppel else ""}"><div class="l">Evtl. doppelt</div><div class="w">{doppel}</div></div>
  </div>
  <form class="auswahl-form" hx-post="/api/abgleich/aktion" hx-target="#main" data-ansicht="abgleich">
    <input type="hidden" name="jahr" value="{jahr}"><input type="hidden" name="filter" value="{filter}">
    <div class="klebe-leiste">
    <div class="row zwischen"><div class="tabs reiter abgleich-tabs">{tabs}</div>
      <span class="row" style="margin:0;gap:.8rem"><input type="search" class="listen-suche" placeholder="in dieser Liste suchen …" aria-label="In der Liste suchen">
      <span class="muted klein listen-zaehler"></span><label class="check klein"><input type="checkbox" class="alle"> alle auswählen</label></span></div>
    {'<p class="muted klein hinweis-rueckfrage">Betrag passt, Datum liegt außerhalb der ±5 Tage. In der Auswahlliste steht die Rechnung mit dem nächsten Datum oben. Alle anhaken und „Rückfragen zuordnen“ übernimmt genau diese.</p>' if filter == "rueckfrage" else ''}
    <div class="auswahl-leiste" hidden><span class="anzahl"></span>
      <button type="submit" name="aktion" value="zuordnen" class="btn-primary klein" title="Jede ausgewählte Rückfrage bekommt die Rechnung mit gleichem Betrag und dem nächsten Datum">Rückfragen zuordnen</button>
      <button type="submit" name="aktion" value="anlegen" class="{"btn-secondary" if filter == "rueckfrage" else "btn-primary"} klein">Buchungen anlegen</button>
      <button type="submit" name="aktion" value="ignorieren" class="btn-secondary klein">Ignorieren</button>
      <button type="submit" name="aktion" value="regel" class="btn-ghost klein" hx-confirm="Für jede ausgewählte Bewegung eine Ignorier-Regel auf das Gegenkonto anlegen?">Immer ignorieren</button>
      <button type="submit" name="aktion" value="loesen" class="btn-ghost klein">Zuordnung lösen</button></div>
    </div>
    <div class="scroll"><table class="tabelle kompakt abgleich-tabelle"><colgroup><col class="c-wahl"><col class="c-datum"><col class="c-betrag"><col class="c-zweck"><col class="c-status"><col class="c-aktion"></colgroup><thead><tr><th></th><th class="sortierbar" data-sort="datum" title="nach Datum sortieren">Datum <span class="pfeil"></span></th><th class="num sortierbar" data-sort="betrag" title="nach Betrag sortieren">Betrag <span class="pfeil"></span></th><th>Gegenkonto / Zweck</th><th class="sortierbar" data-sort="status" title="nach Status sortieren: Rückfragen, Dubletten, ohne Beleg, zugeordnet, ignoriert">Abgleich <span class="pfeil"></span></th><th class="aktion-kopf">Aktion</th></tr></thead>
    <tbody>{rows or '<tr><td colspan=6 class="muted">Nichts in dieser Liste.</td></tr>'}</tbody></table></div>
  </form>
  <details class="karte" {"open" if regeln else ""}><summary><strong>Ignorier-Regeln</strong> <span class="muted">({len(regeln)}) – Bewegungen, die nie betrieblich sind</span></summary>
    <ul class="klein regeln-liste">{regeln_html or '<li class="muted">Noch keine Regeln. „immer ignorieren“ an einer Zeile legt eine an.</li>'}</ul>
    <form class="row inline" hx-post="/api/ignorregel/neu" hx-target="#main"><input type="hidden" name="jahr" value="{jahr}"><input type="hidden" name="filter" value="{filter}">
      <input name="muster" placeholder="z. B. netflix oder Miete" required> <button class="klein btn-secondary">Regel anlegen</button></form>
  </details>
</section>
<script>
(function(){{
  document.querySelectorAll('.auswahl-form').forEach(f => {{
    const leiste = f.querySelector('.auswahl-leiste'), alle = f.querySelector('input.alle');
    const boxen = () => [...f.querySelectorAll('tbody input[type=checkbox]')];
    function zaehlen(){{ const n = boxen().filter(b => b.checked).length; leiste.hidden = !n; leiste.querySelector('.anzahl').textContent = n + ' ausgewählt ·'; }}
    if (alle) alle.addEventListener('change', () => {{ boxen().filter(b => !b.closest('tr').hidden).forEach(b => b.checked = alle.checked); zaehlen(); }});
    f.addEventListener('change', e => {{ if (e.target.type === 'checkbox' && e.target !== alle) zaehlen(); }});
    // Suche innerhalb der Liste
    const suche = f.querySelector('.listen-suche'), zaehler = f.querySelector('.listen-zaehler'), tbody = f.querySelector('tbody');
    const zeilen = () => [...tbody.querySelectorAll('tr[data-datum]')];
    function filtern(){{
      const q = (suche.value || '').trim().toLowerCase(); let n = 0;
      zeilen().forEach(tr => {{ const ok = !q || tr.textContent.toLowerCase().includes(q); tr.hidden = !ok; if (ok) n++; }});
      zaehler.textContent = q ? n + ' von ' + zeilen().length : '';
    }}
    // Zustand (Suche, Sortierung) überlebt jede Aktion: die Liste wird vom Server neu aufgebaut, danach hier wiederhergestellt
    const speicher = {{ lesen(){{ try {{ return JSON.parse(sessionStorage.getItem('abgleich-zustand') || '{{}}'); }} catch (e) {{ return {{}}; }} }},
                       schreiben(z){{ try {{ sessionStorage.setItem('abgleich-zustand', JSON.stringify(z)); }} catch (e) {{}} }} }};
    const zustand = speicher.lesen();
    if (suche) suche.addEventListener('input', () => {{ filtern(); zustand.suche = suche.value; speicher.schreiben(zustand); }});
    // Sortieren per Klick auf Datum/Betrag/Abgleich (Status: Rückfrage → Dublette → kein Beleg → zugeordnet → ignoriert, gleiche Stufe nach Datum absteigend)
    let sortKey = null, sortDir = -1;
    const vgl = (a, b, key) => {{ const va = a.dataset[key], vb = b.dataset[key]; return (key === 'betrag' || key === 'status') ? (+va - +vb) : (va < vb ? -1 : va > vb ? 1 : 0); }};
    function sortieren(key, dir){{
      sortKey = key; sortDir = dir;
      const rows = zeilen(); rows.sort((a, b) => {{ const r = vgl(a, b, key) * sortDir; return r || (key === 'status' ? -vgl(a, b, 'datum') : 0); }});
      rows.forEach(r => tbody.appendChild(r));
      f.querySelectorAll('th.sortierbar').forEach(t => {{ const an = t.dataset.sort === key; t.classList.toggle('aktiv', an); t.querySelector('.pfeil').textContent = an ? (sortDir > 0 ? '▲' : '▼') : ''; }});
    }}
    f.querySelectorAll('th.sortierbar').forEach(th => th.addEventListener('click', () => {{
      const key = th.dataset.sort; sortieren(key, (sortKey === key) ? -sortDir : (key === 'datum' ? -1 : 1));
      zustand.sort = key; zustand.dir = sortDir; speicher.schreiben(zustand);
    }}));
    if (suche && zustand.suche) {{ suche.value = zustand.suche; filtern(); }}
    if (zustand.sort && f.querySelector('th[data-sort="' + zustand.sort + '"]')) sortieren(zustand.sort, zustand.dir || 1);
  }});
}})();
</script>"""


# ---------------------------------------------------------------- Suche

def suche_view(q: str, treffer: list[Buchung], kategorien: dict[int, Kategorie], mit_konto: set) -> str:
    def status(b: Buchung) -> str:
        if b.storniert:
            return '<span class="badge">storniert</span>'
        if b.status == "bestaetigt":
            return '<span class="badge ok">bestätigt</span>'
        return '<span class="badge mid">Vorschlag</span>'
    def konto_badge(b: Buchung) -> str:
        return '<span class="badge ok" title="Kontobewegung zugeordnet">Konto ✓</span>' if b.id in mit_konto else ""
    rows = "".join(
        f'<tr><td>{d(b.datum)}</td><td><span class="badge {"plus-b" if b.richtung == "einnahme" else "minus-b"}">{"Einnahme" if b.richtung == "einnahme" else "Ausgabe"}</span></td>'
        f'<td>{h(b.lieferant)}<div class="muted klein">{h(b.beschreibung[:80])}{(" · " + h(b.rechnungsnummer)) if b.rechnungsnummer else ""}</div></td>'
        f'<td class="num">{eur_fmt(b.betrag_brutto)}</td><td>{h(kategorien[b.kategorie_id].name) if b.kategorie_id in kategorien else "–"}</td>'
        f'<td>{status(b)} {konto_badge(b)}</td>'
        f'<td class="aktionen-zelle"><a href="#" class="btn-ghost" hx-get="/ui/pruefen/{b.id}" hx-target="#main" title="Beleg öffnen und korrigieren">{ICON["stift"]}Korrigieren</a></td></tr>'
        for b in treffer)
    summe = sum(b.betrag_brutto for b in treffer)
    return f"""
<section>
  <p class="muted erkl">{f"{len(treffer)} Treffer für „{h(q)}“ · Summe {eur_fmt(summe)}" if q else "Suchbegriff oben eingeben: Lieferant, Beschreibung, Rechnungsnummer, Betrag oder Datum."}</p>
  <div class="scroll"><table class="tabelle kompakt"><thead><tr><th>Datum</th><th>Art</th><th>Lieferant / Kunde</th><th class="num">Brutto</th><th>Kategorie</th><th>Status</th><th></th></tr></thead>
  <tbody>{rows or f'<tr><td colspan=7 class="muted">{"Keine Buchung passt." if q else ""}</td></tr>'}</tbody></table></div>
</section>"""
