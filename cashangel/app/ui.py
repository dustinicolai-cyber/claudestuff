"""HTML-Fragmente für die Ansichten. Reine Funktionen: Daten rein, HTML raus."""
from __future__ import annotations

import html as _html
import json
from datetime import date

from .analyse import eur
from .models import AboStatus, Bewegung, Kategorie, Regel

ICON = {
    "stift": '<svg viewBox="0 0 24 24"><path d="M4 20h4l10.5-10.5a2 2 0 0 0 0-2.8l-1.2-1.2a2 2 0 0 0-2.8 0L4 16v4z"/><path d="M13 7l4 4"/></svg>',
    "x": '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    "auge_zu": '<svg viewBox="0 0 24 24"><path d="M3 3l18 18"/><path d="M10.6 10.6A2.5 2.5 0 0 0 13.4 13.4"/><path d="M9.9 5.2A10.4 10.4 0 0 1 12 5c5 0 8.5 4 9.5 7a13 13 0 0 1-2.8 3.9"/><path d="M6.6 6.6C4.6 8 3.2 10 2.5 12c1 3 4.5 7 9.5 7a9.7 9.7 0 0 0 4.1-.9"/></svg>',
    "check": '<svg viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg>',
    "upload": '<svg viewBox="0 0 24 24"><path d="M12 16V4m-5 5l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>',
}


def h(x) -> str:
    return _html.escape(str(x if x is not None else ""), quote=True)


def d(x: date | None) -> str:
    return x.strftime("%d.%m.%Y") if x else "–"


def meldung_box(text: str, cls: str = "ok-box") -> str:
    return f'<p class="{cls}" role="{"alert" if cls == "fehler-box" else "status"}"><span>{h(text)}</span></p>'


def leer_view() -> str:
    return """
<section class="leer-start">
  <div class="karte hero">
    <h2>Willkommen bei Cash Angel</h2>
    <p class="muted">Lade einen Kontoauszug (CSV, CAMT.053 oder PDF deiner Bank), dann zeigt dir Cash Angel, wo das Geld jeden Monat hingeht,
    welche Abos laufen und welche Gewohnheiten dahinterstecken. Alles bleibt auf diesem Rechner.</p>
    <p><a class="button btn-primary" href="#" hx-get="/ui/import" hx-target="#main">Kontoauszug laden</a></p>
  </div>
</section>"""


# ---------------------------------------------------------------- Übersicht

def uebersicht_view(zeitraum: str, beschriftung: str) -> str:
    return f"""
<section id="uebersicht" data-zeitraum="{h(zeitraum)}">
  <div class="kpis" id="kpis">
    <div class="kpi"><div class="l">Einnahmen · Ø Monat</div><div class="w" id="kpi-ein">–</div><div class="klein muted" id="kpi-ein-sub"></div></div>
    <div class="kpi"><div class="l">Ausgaben · Ø Monat</div><div class="w" id="kpi-aus">–</div><div class="klein muted" id="kpi-aus-sub"></div></div>
    <div class="kpi" id="kpi-saldo-box"><div class="l">Übrig · Ø Monat</div><div class="w" id="kpi-saldo">–</div><div class="klein muted" id="kpi-saldo-sub"></div></div>
    <div class="kpi"><div class="l">Sparquote</div><div class="w" id="kpi-quote">–</div><div class="klein muted" id="kpi-quote-sub"></div></div>
    <div class="kpi"><div class="l">Abos &amp; Verträge</div><div class="w" id="kpi-abos">–</div><div class="klein muted" id="kpi-abos-sub"></div></div>
  </div>
  <div class="karte chart-karte">
    <div class="row zwischen"><h3 style="margin:0">Einnahmen und Ausgaben je Monat</h3><span class="muted klein">{h(beschriftung)}</span></div>
    <div class="legende" id="leg-monate"></div>
    <div class="chart-wrap"><svg id="chart-monate" viewBox="0 0 960 340" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Monatsbalken"></svg><div class="tooltip" id="tip-monate" hidden></div></div>
  </div>
  <div class="karten zwei">
    <div class="karte chart-karte"><h3 style="margin:0 0 .4rem">Woher kommt das Geld</h3>
      <div class="chart-wrap donut"><svg id="chart-ein" viewBox="0 0 480 300" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Einnahmequellen"></svg><div class="tooltip" id="tip-ein" hidden></div></div></div>
    <div class="karte chart-karte"><h3 style="margin:0 0 .4rem">Wohin geht das Geld</h3>
      <div class="chart-wrap donut"><svg id="chart-aus" viewBox="0 0 480 300" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Ausgaben nach Kategorie"></svg><div class="tooltip" id="tip-aus" hidden></div></div></div>
  </div>
  <div class="karte"><div class="row zwischen"><h3 style="margin:0">Ausgaben nach Kategorie</h3><span class="muted klein">Ø pro Monat · Klick öffnet die Buchungen</span></div>
    <div id="kat-liste" class="kat-liste"></div></div>
</section>
<script>
(function(){{
  const wurzel = document.getElementById('uebersicht'); if (!wurzel) return;
  const z = wurzel.dataset.zeitraum;
  fetch('/api/uebersicht?zeitraum=' + encodeURIComponent(z)).then(r => r.json()).then(d => {{
    const n = Math.max(1, d.monate_mit_daten);
    const setz = (id, t) => document.getElementById(id).textContent = t;
    setz('kpi-ein', CA.eur(d.schnitt.einnahmen)); setz('kpi-ein-sub', 'gesamt ' + CA.eur(d.summe.einnahmen) + ' in ' + n + ' Monaten');
    setz('kpi-aus', CA.eur(d.schnitt.ausgaben)); setz('kpi-aus-sub', 'davon fix ' + CA.eur(d.schnitt.fix) + ' · variabel ' + CA.eur(d.schnitt.variabel));
    setz('kpi-saldo', CA.eur(d.schnitt.saldo)); setz('kpi-saldo-sub', (d.schnitt.gespart ? 'davon ' + CA.eur(d.schnitt.gespart) + ' per Sparplan · ' : '') + 'gesamt ' + CA.eur(d.summe.saldo));
    document.getElementById('kpi-saldo-box').classList.add(d.schnitt.saldo >= 0 ? 'plus' : 'minus');
    setz('kpi-quote', d.summe.sparquote == null ? '–' : d.summe.sparquote.toLocaleString('de-DE') + ' %'); setz('kpi-quote-sub', 'Anteil der Einnahmen, der übrig bleibt');
    setz('kpi-abos', CA.eur(d.abos.monatlich)); setz('kpi-abos-sub', d.abos.anzahl + ' laufende · ' + CA.eur(d.abos.monatlich * 12) + ' im Jahr');
    CA.gruppen('chart-monate', 'tip-monate', 'leg-monate', d.monate.map(m => m.name.replace(' 20', ' ’')), [
      {{name: 'Einnahmen', farbe: CA.css('--plus'), werte: d.monate.map(m => m.einnahmen)}},
      {{name: 'Ausgaben', farbe: CA.css('--minus'), werte: d.monate.map(m => m.ausgaben)}}]);
    CA.donut('chart-ein', 'tip-ein', d.einnahmequellen.map(e => ({{name: e.name, wert: e.wert}})), 'Einnahmen', CA.palette('plus'));
    CA.donut('chart-aus', 'tip-aus', d.kategorien.map(k => ({{name: k.name, wert: k.wert, farbe: k.farbe}})), 'Ausgaben', null);
    const max = Math.max(1, ...d.kategorien.map(k => k.wert));
    document.getElementById('kat-liste').innerHTML = d.kategorien.map(k => `
      <a href="#" class="kat-zeile" hx-get="/ui/buchungen?kategorie=${{k.schluessel}}" hx-target="#main">
        <span class="kat-name"><i style="background:${{k.farbe}}"></i>${{CA.esc(k.name)}}${{k.fix ? ' <span class="badge">fix</span>' : ''}}</span>
        <span class="kat-balken"><span style="width:${{(k.wert / max * 100).toFixed(1)}}%;background:${{k.farbe}}"></span></span>
        <span class="kat-wert">${{CA.eur(k.wert / n)}}<small> · ${{(k.wert / Math.max(1, d.summe.ausgaben) * 100).toFixed(0)}} %</small></span></a>`).join('');
    htmx.process(document.getElementById('kat-liste'));
  }});
}})();
</script>"""


# ---------------------------------------------------------------- Abos

def abos_view(abos: list[dict], status: dict[str, AboStatus]) -> str:
    aktiv = [a for a in abos if a["aktiv"] and status.get(a["partner"], AboStatus()).status == "ok"]
    inaktiv = [a for a in abos if a not in aktiv]
    monat = sum(a["monatlich"] for a in aktiv)

    def zeile(a: dict) -> str:
        st = status.get(a["partner"])
        st_txt = {"gekuendigt": '<span class="badge ok">gekündigt</span>', "kein_abo": '<span class="badge">kein Abo</span>'}.get(st.status if st else "", "")
        if not st_txt and not a["aktiv"]:
            st_txt = '<span class="badge mid">ausgelaufen?</span>'
        naechste = f'<span class="muted klein">nächste ca. {d(a["naechste"])}</span>' if a["aktiv"] else ""
        return (f'<tr class="{"" if a["aktiv"] else "gedaempft"}"><td><b>{h(a["name"])}</b><div class="klein muted">seit {d(a["seit"])} · {a["anzahl"]}× · zuletzt {d(a["zuletzt"])} {naechste}</div></td>'
                f'<td><span class="kat-punkt" style="background:{h(a["farbe"])}"></span>{h(a["kategorie"])}<div class="klein muted">{h(a["art"])}</div></td>'
                f'<td>{h(a["intervall"])}{"" if a["stabil"] else " <span class=badge title=Betrag_schwankt>schwankt</span>"}</td>'
                f'<td class="num">{eur(a["betrag"])}</td><td class="num fett">{eur(a["monatlich"])}</td><td class="num">{eur(a["jaehrlich"])}</td>'
                f'<td>{st_txt}</td>'
                f'<td class="aktionen-zelle"><form class="inline" hx-post="/api/abo/status" hx-target="#main"><input type="hidden" name="partner" value="{h(a["partner"])}">'
                f'<select name="status" hx-post="/api/abo/status" hx-trigger="change" hx-target="#main" hx-include="closest form">'
                f'<option value="ok" {"selected" if not st or st.status == "ok" else ""}>läuft</option><option value="gekuendigt" {"selected" if st and st.status == "gekuendigt" else ""}>gekündigt</option>'
                f'<option value="kein_abo" {"selected" if st and st.status == "kein_abo" else ""}>kein Abo</option></select></form></td></tr>')

    rows = "".join(zeile(a) for a in aktiv) or '<tr><td colspan=8 class="muted">Noch keine wiederkehrenden Zahlungen erkannt – dafür braucht es mindestens drei Monate Kontoauszüge.</td></tr>'
    rows_inaktiv = "".join(zeile(a) for a in inaktiv)
    return f"""
<section class="abos">
  <p class="muted erkl">Wiederkehrende Zahlungen: gleicher Empfänger, regelmäßiger Abstand, ähnlicher Betrag. Jahres- und Quartalsbeiträge sind auf den Monat umgerechnet.
  Als „gekündigt“ markierte verschwinden aus der Summe; „kein Abo“ für Dinge, die zufällig regelmäßig sind.</p>
  <div class="kpis">
    <div class="kpi"><div class="l">Laufende Abos &amp; Verträge</div><div class="w">{len(aktiv)}</div></div>
    <div class="kpi"><div class="l">Pro Monat</div><div class="w">{eur(monat)}</div></div>
    <div class="kpi"><div class="l">Pro Jahr</div><div class="w">{eur(monat * 12)}</div></div>
    <div class="kpi"><div class="l">Streaming &amp; Abos</div><div class="w">{eur(sum(a["monatlich"] for a in aktiv if a["kategorie_schluessel"] == "abos_streaming"))}</div><div class="klein muted">pro Monat</div></div>
  </div>
  <div class="scroll"><table class="tabelle kompakt abo-tabelle"><thead><tr><th>Empfänger</th><th>Kategorie</th><th>Rhythmus</th><th class="num">Betrag</th><th class="num">pro Monat</th><th class="num">pro Jahr</th><th>Status</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  {f'<h3>Ausgelaufen, gekündigt oder kein Abo ({len(inaktiv)})</h3><div class="scroll"><table class="tabelle kompakt abo-tabelle"><thead><tr><th>Empfänger</th><th>Kategorie</th><th>Rhythmus</th><th class="num">Betrag</th><th class="num">pro Monat</th><th class="num">pro Jahr</th><th>Status</th><th></th></tr></thead><tbody>{rows_inaktiv}</tbody></table></div>' if inaktiv else ''}
</section>"""


# ---------------------------------------------------------------- Buchungen

def buchung_zeile(b: Bewegung, kats: dict[int, Kategorie], personen: list[str], gespeichert: bool = False, hinweis: str = "") -> str:
    k = kats.get(b.kategorie_id or -1)
    art = "einnahme" if b.betrag > 0 else "ausgabe"
    opts = "".join(f'<option value="{x.id}" {"selected" if x.id == b.kategorie_id else ""}>{h(x.name)}</option>'
                   for x in sorted(kats.values(), key=lambda x: x.sortierung) if x.art == art or x.art == "umbuchung")
    p_opts = "".join(f'<option value="{h(p)}" {"selected" if p == b.person else ""}>{h(p)}</option>' for p in personen)
    person = (f'<select name="person" aria-label="Person"><option value="">–</option>{p_opts}</select>'
              if b.betrag > 0 and k and k.schluessel == "gehalt" else f'<input type="hidden" name="person" value="{h(b.person)}">')
    weg = {"muster": "automatisch", "gehalt": "Gehalt erkannt", "umbuchung": "Umbuchung", "manuell": "von Hand", "-": "unklar"}.get(b.weg.split(":")[0], "gelernt")
    return (f'<tr id="bw-{b.id}" class="bw {"gespeichert" if gespeichert else ""} {"ignoriert" if b.ignoriert else ""}" data-datum="{b.datum.isoformat()}" data-betrag="{b.betrag:.2f}" '
            f'hx-post="/api/bewegung/{b.id}/kategorie" hx-trigger="change[target.name!=\'ids\']" hx-include="closest tr" hx-target="this" hx-swap="outerHTML" hx-disinherit="*">'
            f'<td><input type="checkbox" name="ids" value="{b.id}" class="bw-wahl" aria-label="auswählen"></td>'
            f'<td class="nowrap">{d(b.datum)}<div class="klein muted">{["Mo","Di","Mi","Do","Fr","Sa","So"][b.datum.weekday()]}</div></td>'
            f'<td class="num {"plus" if b.betrag > 0 else "minus"}">{eur(b.betrag)}</td>'
            f'<td><b>{h(b.gegenkonto or "–")}</b><div class="klein muted zweck">{h(b.verwendungszweck[:120])}</div></td>'
            f'<td><span class="kat-punkt" style="background:{h(k.farbe if k else "#64748b")}"></span><select name="kategorie_id" aria-label="Kategorie">{opts}</select> {person}'
            f'<div class="klein muted">{weg}{(" · " + h(hinweis)) if hinweis else ""}{(" · " + h(b.konto)) if b.konto else ""}</div></td></tr>')


def buchungen_view(zeilen: list[Bewegung], kats: dict[int, Kategorie], personen: list[str], zeitraum: str, kategorie: str, q: str, konto: str,
                   konten: list[str], nur_offen: bool) -> str:
    rows = "".join(buchung_zeile(b, kats, personen) for b in zeilen)
    kat_opts = "".join(f'<option value="{h(k.schluessel)}" {"selected" if k.schluessel == kategorie else ""}>{h(k.name)}</option>'
                       for k in sorted(kats.values(), key=lambda x: (x.art != "einnahme", x.sortierung)))
    konto_opts = "".join(f'<option value="{h(k)}" {"selected" if k == konto else ""}>{h(k)}</option>' for k in konten)
    sammel_opts = (f'<optgroup label="Ausgaben">{"".join(f"<option value={k.id}>{h(k.name)}</option>" for k in sorted(kats.values(), key=lambda x: x.sortierung) if k.art == "ausgabe")}</optgroup>'
                   f'<optgroup label="Einnahmen">{"".join(f"<option value={k.id}>{h(k.name)}</option>" for k in sorted(kats.values(), key=lambda x: x.sortierung) if k.art == "einnahme")}</optgroup>'
                   f'<optgroup label="Umbuchung">{"".join(f"<option value={k.id}>{h(k.name)}</option>" for k in kats.values() if k.art == "umbuchung")}</optgroup>')
    ein = sum(b.betrag for b in zeilen if b.betrag > 0 and not b.ignoriert)
    aus = sum(-b.betrag for b in zeilen if b.betrag < 0 and not b.ignoriert)
    return f"""
<section class="buchungen" id="buchungen">
  <form class="filter row" hx-get="/ui/buchungen" hx-target="#main" hx-trigger="change, submit, input changed delay:350ms from:input[name=q]">
    <input type="hidden" name="zeitraum" value="{h(zeitraum)}">
    <input type="search" name="q" value="{h(q)}" placeholder="Suchen … (Empfänger, Zweck, Betrag)" class="suchfeld">
    <select name="kategorie"><option value="">alle Kategorien</option>{kat_opts}</select>
    {f'<select name="konto"><option value="">alle Konten</option>{konto_opts}</select>' if konten else ''}
    <label class="check"><input type="checkbox" name="nur_offen" value="1" {"checked" if nur_offen else ""}> nur unklare</label>
    <span class="muted klein">{len(zeilen)} Buchungen · <span class="plus">{eur(ein)}</span> ein · <span class="minus">{eur(aus)}</span> aus</span>
    <a class="btn-ghost klein" href="/api/export/buchungen.csv?zeitraum={h(zeitraum)}" download>CSV</a>
  </form>
  <form class="bw-aktion" hx-post="/api/bewegungen/aktion" hx-target="#main" hx-include="#buchungen .bw-wahl:checked" aria-hidden="true">
    <input type="hidden" name="zeitraum" value="{h(zeitraum)}"><input type="hidden" name="kategorie" value="{h(kategorie)}"><input type="hidden" name="q" value="{h(q)}"><input type="hidden" name="konto" value="{h(konto)}"><input type="hidden" name="nur_offen" value="{"1" if nur_offen else ""}">
    <label for="bw-kat">Kategorie für die Auswahl <span class="anzahl muted"></span></label>
    <select name="kategorie_id" id="bw-kat"><option value="">– wählen –</option>{sammel_opts}</select>
    <button type="submit" name="aktion" value="kategorie" class="btn-primary klein">Anwenden</button>
    <button type="submit" name="aktion" value="ignorieren" class="btn-ghost klein" title="zählt nicht mehr mit (z. B. Kreditkartenabrechnung, die doppelt erscheint)">{ICON["auge_zu"]}ausblenden</button>
    <button type="submit" name="aktion" value="freigeben" class="btn-ghost klein">wieder einblenden</button>
    <button type="submit" name="aktion" value="loeschen" class="btn-ghost klein gefahr-text" hx-confirm="Ausgewählte Buchungen wirklich löschen?" data-confirm-vorlage="{{n}} Buchungen wirklich löschen? Ein erneuter Import desselben Auszugs bringt sie nicht zurück.">{ICON["x"]}löschen</button>
  </form>
  <div class="scroll"><table class="tabelle kompakt bw-tabelle"><colgroup><col class="c-wahl"><col class="c-datum"><col class="c-betrag"><col class="c-partner"><col class="c-kat"></colgroup>
    <thead><tr><th><input type="checkbox" class="bw-alle" aria-label="alle auswählen"></th><th class="sortierbar" data-sort="datum">Datum <span class="pfeil"></span></th><th class="num sortierbar" data-sort="betrag">Betrag <span class="pfeil"></span></th><th>Empfänger / Zweck</th><th>Kategorie</th></tr></thead>
    <tbody>{rows or '<tr><td colspan=5 class="muted">Keine Buchungen in dieser Auswahl.</td></tr>'}</tbody></table></div>
  <p class="muted klein">Kategorie in der Zeile ändern speichert sofort und lernt die Zuordnung für denselben Empfänger. Ausgeblendete Zeilen zählen in keiner Auswertung. Sparpläne gelten als gespart, nicht als Ausgabe.</p>
</section>
<script>
(function(){{
  const box = document.getElementById('buchungen'), tbody = box.querySelector('tbody'), leiste = box.querySelector('.bw-aktion'), alle = box.querySelector('.bw-alle');
  const wahl = () => [...box.querySelectorAll('.bw-wahl')];
  function zaehlen(){{ const n = wahl().filter(b => b.checked).length; leiste.classList.toggle('aktiv', n > 0); leiste.setAttribute('aria-hidden', n ? 'false' : 'true');
    leiste.querySelector('.anzahl').textContent = n ? '(' + n + ')' : ''; if (alle) alle.checked = n > 0 && n === wahl().length;
    leiste.querySelectorAll('[data-confirm-vorlage]').forEach(k => k.setAttribute('hx-confirm', k.dataset.confirmVorlage.replace('{{n}}', n))); }}
  box.addEventListener('change', e => {{ if (e.target.classList.contains('bw-wahl')) zaehlen(); }});
  if (alle) alle.addEventListener('change', () => {{ wahl().forEach(b => b.checked = alle.checked); zaehlen(); }});
  let letzte = null;
  box.addEventListener('click', e => {{ if (!e.target.classList.contains('bw-wahl')) return; const b = wahl(), i = b.indexOf(e.target);
    if (e.shiftKey && letzte !== null) {{ const [a, z] = [Math.min(i, letzte), Math.max(i, letzte)]; for (let k = a; k <= z; k++) b[k].checked = e.target.checked; zaehlen(); }} letzte = i; }});
  let sortKey = null, sortDir = -1;
  box.querySelectorAll('th.sortierbar').forEach(th => th.addEventListener('click', () => {{
    const key = th.dataset.sort; sortDir = (sortKey === key) ? -sortDir : (key === 'datum' ? -1 : 1); sortKey = key;
    const rows = [...tbody.querySelectorAll('tr.bw')]; rows.sort((a, b) => {{ const va = a.dataset[key], vb = b.dataset[key]; return (key === 'betrag' ? (+va - +vb) : (va < vb ? -1 : va > vb ? 1 : 0)) * sortDir; }});
    rows.forEach(r => tbody.appendChild(r));
    box.querySelectorAll('th.sortierbar').forEach(t => {{ const an = t === th; t.classList.toggle('aktiv', an); t.querySelector('.pfeil').textContent = an ? (sortDir > 0 ? '▲' : '▼') : ''; }});
  }}));
}})();
</script>"""


# ---------------------------------------------------------------- Import

def import_view(konten: list[str], dateien: list[tuple[str, int]]) -> str:
    konto_liste = "".join(f'<option value="{h(k)}">' for k in konten)
    dateien_html = "".join(f'<li><code>{h(n)}</code> <span class="muted klein">{z} Buchungen</span></li>' for n, z in dateien)
    return f"""
<section class="import">
  <p class="muted erkl">Kontoauszüge als CSV-Export der Bank, CAMT.053-XML oder PDF. Mehrere Dateien auf einmal sind möglich; schon bekannte Buchungen werden übersprungen.
  Jede Buchung wird sofort einer Kategorie zugeordnet – Gehälter nach Person, Umbuchungen zwischen eigenen Konten zählen nicht.</p>
  <form hx-post="/api/import" hx-target="#main" hx-encoding="multipart/form-data" class="karte import-form">
    <label class="dropzone" id="dropzone">
      <div class="dz-icon">{ICON["upload"]}</div>
      <strong>Kontoauszug hier ablegen oder klicken</strong>
      <span class="muted">CSV · CAMT.053 · PDF – ING, Sparkasse, Volksbank, DKB, comdirect, N26 …</span>
      <input type="file" name="datei" multiple accept=".csv,.txt,.xml,.pdf" hidden required>
      <span class="muted klein" id="dz-namen"></span>
    </label>
    <div class="row">
      <label>Konto (optional, zum Unterscheiden) <input name="konto" list="konten" placeholder="z. B. Gemeinschaftskonto" autocomplete="off"><datalist id="konten">{konto_liste}</datalist></label>
      <button class="btn-primary" style="align-self:flex-end">Einlesen</button>
    </div>
  </form>
  {f'<h3>Bisher geladen</h3><ul class="klein dateien">{dateien_html}</ul>' if dateien else ''}
</section>
<script>
(function(){{
  const dz = document.getElementById('dropzone'), inp = dz.querySelector('input[type=file]'), namen = document.getElementById('dz-namen');
  const zeigen = () => namen.textContent = inp.files.length ? [...inp.files].map(f => f.name).join(', ') : '';
  inp.addEventListener('change', zeigen);
  ['dragenter','dragover'].forEach(ev => dz.addEventListener(ev, e => {{ e.preventDefault(); dz.classList.add('aktiv'); }}));
  ['dragleave','drop'].forEach(ev => dz.addEventListener(ev, e => {{ e.preventDefault(); dz.classList.remove('aktiv'); }}));
  dz.addEventListener('drop', e => {{ inp.files = e.dataTransfer.files; zeigen(); }});
}})();
</script>"""


# ---------------------------------------------------------------- Muster (Psychologie & Sparpotenzial)

def muster_view(ins: dict, zeitraum: str, beschriftung: str) -> str:
    def karte(k: dict) -> str:
        cls = {"gut": "gut", "warn": "warn", "tipp": "tipp", "info": "info"}.get(k["typ"], "info")
        betrag = f'<div class="ins-betrag">{eur(k["betrag"])}</div>' if k.get("betrag") is not None else ""
        link = f'<a href="#" class="klein" hx-get="/ui/buchungen?kategorie={h(k["kategorie"])}" hx-target="#main">Buchungen ansehen</a>' if k.get("kategorie") else ""
        return f'<div class="ins {cls}"><div class="ins-kopf"><b>{h(k["titel"])}</b>{betrag}</div><p>{h(k["text"])} {link}</p></div>'

    top_s = "".join(f'<tr><td><span class="kat-punkt" style="background:{h(p["farbe"])}"></span>{h(p["name"])}<div class="klein muted">{h(p["kategorie"])}</div></td><td class="num">{p["anzahl"]}×</td><td class="num fett">{eur(p["summe"])}</td></tr>' for p in ins["top_summe"])
    top_n = "".join(f'<tr><td><span class="kat-punkt" style="background:{h(p["farbe"])}"></span>{h(p["name"])}<div class="klein muted">{h(p["kategorie"])}</div></td><td class="num fett">{p["anzahl"]}×</td><td class="num">{eur(p["summe"])}</td></tr>' for p in ins["top_anzahl"])
    gross = "".join(f'<tr><td>{h(p["datum"][8:10])}.{h(p["datum"][5:7])}.{h(p["datum"][:4])}</td><td>{h(p["name"])}</td><td class="num fett">{eur(p["betrag"])}</td></tr>' for p in ins["groesste"])
    return f"""
<section id="muster" data-zeitraum="{h(zeitraum)}">
  <p class="muted erkl">Nicht die Zahlen, sondern die Gewohnheiten dahinter: Wann wird ausgegeben, wie oft, in welchen Stückelungen. Zeitraum: {h(beschriftung)}, Werte je Monat.</p>
  <div class="ins-liste">{''.join(karte(k) for k in ins["karten"])}</div>
  <div class="karten zwei">
    <div class="karte chart-karte"><h3 style="margin:0 0 .3rem">Variable Ausgaben nach Wochentag</h3><p class="muted klein" style="margin:0 0 .5rem">Ø pro Monat, ohne Fixkosten, Sparen und Bargeld</p>
      <div class="chart-wrap flach"><svg id="chart-wt" viewBox="0 0 480 240" preserveAspectRatio="xMidYMid meet" role="img"></svg><div class="tooltip" id="tip-wt" hidden></div></div></div>
    <div class="karte chart-karte"><h3 style="margin:0 0 .3rem">Verlauf im Monat</h3><p class="muted klein" style="margin:0 0 .5rem">Tag 1–10, 11–20, 21–Ende · Ø pro Monat</p>
      <div class="chart-wrap flach"><svg id="chart-dr" viewBox="0 0 480 240" preserveAspectRatio="xMidYMid meet" role="img"></svg><div class="tooltip" id="tip-dr" hidden></div></div></div>
  </div>
  <div class="karten drei">
    <div class="karte"><h3 style="margin:0 0 .5rem">Wo das meiste Geld hingeht</h3><table class="tabelle kompakt"><tbody>{top_s or '<tr><td class=muted>–</td></tr>'}</tbody></table></div>
    <div class="karte"><h3 style="margin:0 0 .5rem">Wo am häufigsten gezahlt wird</h3><table class="tabelle kompakt"><tbody>{top_n or '<tr><td class=muted>–</td></tr>'}</tbody></table></div>
    <div class="karte"><h3 style="margin:0 0 .5rem">Größte Einzelausgaben</h3><table class="tabelle kompakt"><tbody>{gross or '<tr><td class=muted>–</td></tr>'}</tbody></table></div>
  </div>
</section>
<script>
(function(){{
  const w = document.getElementById('muster'); if (!w) return;
  fetch('/api/muster?zeitraum=' + encodeURIComponent(w.dataset.zeitraum)).then(r => r.json()).then(d => {{
    CA.gruppen('chart-wt', 'tip-wt', null, d.wochentage.map(x => x.tag), [{{name: 'Ausgaben', farbe: CA.css('--akzent'), werte: d.wochentage.map(x => x.summe)}}], {{L: 60, R: 460, T: 16, B: 200, we: [5, 6]}});
    CA.gruppen('chart-dr', 'tip-dr', null, ['1.–10.', '11.–20.', '21.–Ende'], [{{name: 'Ausgaben', farbe: CA.css('--lila'), werte: d.drittel}}], {{L: 60, R: 460, T: 16, B: 200}});
  }});
}})();
</script>"""


# ---------------------------------------------------------------- Einstellungen

def einstellungen_view(cfg: dict, kats: list[Kategorie], regeln: list[Regel], db_pfad: str, version: str) -> str:
    kat_by_id = {k.id: k for k in kats}
    regeln_html = "".join(f'<tr><td><code>{h(r.muster)}</code></td><td>{h(kat_by_id[r.kategorie_id].name) if r.kategorie_id in kat_by_id else "?"}</td><td>{h(r.person)}</td>'
                          f'<td><button class="klein btn-ghost gefahr-text" hx-post="/api/regel/{r.id}/loeschen" hx-target="#main">entfernen</button></td></tr>' for r in regeln)
    kat_html = "".join(f'<li><span class="kat-punkt" style="background:{h(k.farbe)}"></span>{h(k.name)} <span class="muted klein">{h(k.art)}{" · fix" if k.fix else ""}</span></li>'
                       for k in sorted(kats, key=lambda x: x.sortierung))
    return f"""
<section class="einstellungen">
  <div class="karte"><h3 style="margin-top:0">Haushalt</h3>
    <form hx-post="/api/einstellungen" hx-target="#main" class="stapel">
      <label>Personen (für „Gehalt Susanne“, „Gehalt Dustin“) <input name="personen" value="{h(', '.join(cfg.get('personen', [])))}" placeholder="Susanne, Dustin"></label>
      <label>Eigene IBANs (Umbuchungen zwischen diesen Konten zählen nicht als Einnahme/Ausgabe) <input name="eigene_ibans" value="{h(', '.join(cfg.get('eigene_ibans', [])))}" placeholder="DE12 …, DE34 …"></label>
      <label>Kleinbetrag-Grenze für den Latte-Faktor (€) <input name="kleinbetrag_grenze" type="number" step="1" value="{cfg.get('kleinbetrag_grenze', 15)}" style="width:8em"></label>
      <div><button class="btn-primary">Speichern und neu zuordnen</button></div>
    </form></div>
  <div class="karte"><h3 style="margin-top:0">Gelernte Zuordnungen ({len(regeln)})</h3>
    <p class="muted klein">Entstehen, wenn du in der Buchungsliste eine Kategorie änderst. Gelten für alle Buchungen desselben Empfängers, auch künftige.</p>
    <table class="tabelle kompakt"><thead><tr><th>Empfänger</th><th>Kategorie</th><th>Person</th><th></th></tr></thead><tbody>{regeln_html or '<tr><td colspan=4 class="muted">Noch keine.</td></tr>'}</tbody></table>
    <form class="row" hx-post="/api/neu-klassifizieren" hx-target="#main" style="margin-top:.8rem">
      <button class="btn-secondary klein">Automatik erneut anwenden</button>
      <label class="check klein"><input type="checkbox" name="alle" value="1"> auch von Hand gesetzte überschreiben</label></form></div>
  <div class="karte"><h3 style="margin-top:0">Kategorien ({len(kats)})</h3>
    <p class="muted klein">Namen, Farben und Erkennungsmuster stehen in <code>kategorien.json</code> im Datenordner. Eigene Muster dort ergänzen, dann „Automatik erneut anwenden“.</p>
    <ul class="kat-ul">{kat_html}</ul></div>
  <div class="karte"><h3 style="margin-top:0">Dateien</h3>
    <p>Datenbank: <code>{h(db_pfad)}</code><br>Version <code>{h(version)}</code> · lokal, offline, keine Telemetrie.</p>
    <div class="row"><button class="gefahr" hx-post="/api/beenden" hx-target="#main" hx-confirm="Cash Angel beenden? Der Server wird gestoppt; alle Daten sind gespeichert.">Cash Angel beenden</button></div></div>
</section>"""
