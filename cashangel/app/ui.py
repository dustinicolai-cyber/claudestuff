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
    CA.donut('chart-ein', 'tip-ein', d.einnahmequellen.map(e => ({{name: e.name, wert: e.wert, farbe: e.farbe}})), 'Einnahmen', CA.palette('plus'));
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

# (Schlüssel, Überschrift, Unterzeile, kurzer Name für die Kreismitte, Farbvariable)
TYPEN = [("abo", "Abos", "Streaming, Software, Mitgliedschaften", "Abos", "--lila"),
         ("vertrag", "Verträge", "Miete, Strom, Telefon, Daueraufträge", "Verträge", "--akzent"),
         ("krankenkasse", "Versicherung & Krankenkasse", "Beiträge zur Vorsorge", "Versicherung", "--dunkelblau"),
         ("depot", "Depots & Sparpläne", "Geld, das im Haushalt bleibt", "Depots", "--tuerkis"),
         ("kredit", "Kredite & Raten", "Tilgung und Finanzierung", "Kredite", "--minus")]


def abos_view(abos: list[dict], status: dict[str, AboStatus], ausgaben_monat: float = 0.0, einnahmen_monat: float = 0.0,
              kats: dict[int, Kategorie] | None = None, gespeichert: str = "", vorschlaege: list[dict] | None = None) -> str:
    kats = kats or {}
    vorschlaege = vorschlaege or []
    ausgabe_kats = [k for k in sorted(kats.values(), key=lambda x: x.sortierung) if k.art in ("ausgabe", "einnahme")]

    def kat_opts(schluessel: str) -> str:
        return "".join(f'<option value="{k.id}" {"selected" if k.schluessel == schluessel else ""}>{h(k.name)}</option>' for k in ausgabe_kats)

    def intervall_opts(gewaehlt: str) -> str:
        return "".join(f'<option value="{w}" {"selected" if w == gewaehlt else ""}>{t}</option>'
                       for w, t in (("monatlich", "monatlich"), ("quartal", "vierteljährlich"), ("halbjahr", "halbjährlich"), ("jaehrlich", "jährlich")))

    def typ_opts(gewaehlt: str) -> str:
        eintraege = [(t, name) for t, name, _, _, _ in TYPEN] + [("kein", "kein Vertrag")]
        return "".join(f'<option value="{t}" {"selected" if t == gewaehlt else ""}>{name}</option>' for t, name in eintraege)

    def laeuft(a: dict) -> bool:
        st = status.get(a["partner"])
        return a["aktiv"] and a["typ"] != "kein" and (st is None or st.status == "ok")

    aktiv = [a for a in abos if laeuft(a)]
    ruhend = [a for a in abos if not laeuft(a)]
    monat = sum(a["monatlich"] for a in aktiv)
    groesster = max(aktiv, key=lambda a: a["monatlich"], default=None)

    # ------------------------------------------------------------ eine Karte je Anbieter
    def karte(a: dict, anteil: float) -> str:
        manuell = a.get("manuell", False)
        st = status.get(a["partner"])
        st_status = "ok" if a["aktiv"] and (st is None or st.status == "ok") else "gekuendigt"
        frisch = " frisch" if gespeichert and a["partner"] == gespeichert else ""
        if manuell:
            wert_txt = f"{a['betrag']:.2f}".replace(".", ",")
            wert_feld = f'<input name="betrag" type="text" inputmode="decimal" value="{wert_txt}" class="a-wert" aria-label="Betrag" title="Betrag ändern">'
            rhythmus = f'<select name="intervall" aria-label="Rhythmus">{intervall_opts(a.get("intervall_schluessel", "monatlich"))}</select>'
            meta = f'von Hand · {eur(a["monatlich"])} pro Monat · {eur(a["jaehrlich"])} pro Jahr'
            weg = (f'<button type="button" class="a-weg" hx-post="/api/abo/manuell/{a["manuell_id"]}/loeschen" hx-target="#main" '
                   f'hx-confirm="„{h(a["name"])}“ entfernen?" title="Eintrag entfernen" aria-label="Eintrag entfernen">{ICON["x"]}</button>')
        else:
            wert_txt = format(a["monatlich"], ".2f").replace(".", ",")
            wert_feld = f'<input name="monatlich" type="text" inputmode="decimal" value="{wert_txt}" class="a-wert" aria-label="pro Monat" title="Monatsbetrag anpassen">'
            rhythmus = f'<span class="a-chip">{h(a["intervall"])}</span>'
            schwankt = "" if a["stabil"] else " · Betrag schwankt"
            naechste = f' · nächste ca. {d(a["naechste"])}' if a["aktiv"] else " · zuletzt " + d(a["zuletzt"])
            meta = f'{eur(a["betrag"])} je Zahlung · {a["anzahl"]}× seit {d(a["seit"])}{naechste}{schwankt}'
            weg = ""
        return (f'<article class="anbieter{frisch}" style="--f:{h(a["farbe"])}" hx-post="/api/abo/bearbeiten" hx-trigger="change" '
                f'hx-include="closest .anbieter" hx-target="#main" hx-swap="innerHTML" hx-disinherit="*">'
                f'<input type="hidden" name="partner" value="{h(a["partner"])}">'
                f'<div class="a-kopf"><input name="name" value="{h(a["name"])}" class="a-name" aria-label="Anbieter" title="Anbieter umbenennen">'
                f'{wert_feld}<span class="a-eur">€</span></div>'
                f'<div class="a-balken" title="{prozent_kurz(anteil)} dieses Blocks"><span style="width:{max(2.0, anteil * 100):.1f}%"></span></div>'
                f'<div class="a-meta">{h(meta)}</div>'
                f'<div class="a-felder">{rhythmus}<select name="typ" aria-label="Art" title="Als Abo, Vertrag, Versicherung, Depot oder Kredit einordnen">{typ_opts(a["typ"])}</select>'
                f'<select name="kategorie_id" aria-label="Kategorie">{kat_opts(a["kategorie_schluessel"])}</select>'
                f'<select name="status" aria-label="Status"><option value="ok" {"selected" if st_status == "ok" else ""}>läuft</option>'
                f'<option value="gekuendigt" {"selected" if st_status != "ok" else ""}>gekündigt</option></select>{weg}</div></article>')

    # ------------------------------------------------------------ Box je Art
    vorschlag_opts = "".join(f'<option value="{h(v["partner"])}">{h(v["name"])} · {eur(v["betrag"])} · {h(v["kategorie"])}</option>' for v in vorschlaege)

    def block(typ: str, titel: str, unterzeile: str) -> str:
        eintraege = [a for a in aktiv if a["typ"] == typ]
        summe = sum(a["monatlich"] for a in eintraege)
        karten = "".join(karte(a, (a["monatlich"] / summe) if summe else 0) for a in eintraege)
        vorwahl = {"abo": "abos_streaming", "krankenkasse": "versicherungen", "depot": "sparen", "kredit": "kredit"}.get(typ, "wohnen")
        if eintraege:
            mitte = (f'<div class="chart-wrap rund"><svg id="chart-{typ}" viewBox="0 0 300 300" preserveAspectRatio="xMidYMid meet" role="img" '
                     f'aria-label="{h(titel)} nach Anbieter"></svg><div class="tooltip" id="tip-{typ}" hidden></div></div>'
                     f'<div class="b-summe"><span class="b-zahl">{eur(summe)}<small> / Monat</small></span>'
                     f'<span class="muted klein">{len(eintraege)} {"Eintrag" if len(eintraege) == 1 else "Einträge"} · {eur(summe * 12)} pro Jahr</span></div>')
        else:
            mitte = f'<p class="b-leer muted">Noch nichts unter „{h(titel)}“. Unten einen bekannten Empfänger übernehmen, von Hand eintragen oder in einem anderen Block die Art umstellen.</p>'
        return f"""
    <section class="v-block karte" id="block-{typ}" data-typ="{typ}">
      <header class="b-kopf"><div class="b-titel"><h3>{h(titel)}</h3><p class="muted klein">{h(unterzeile)}</p></div></header>
      {mitte}
      <div class="b-aktionen">
        <form class="b-zuordnung" hx-post="/api/abo/aus-zuordnung" hx-target="#main">
          <input type="hidden" name="typ" value="{typ}">
          <select name="partner" aria-label="Bekannten Empfänger übernehmen" required><option value="">aus Zuordnungen hinzufügen …</option>{vorschlag_opts}</select>
          <button class="btn-secondary klein">Übernehmen</button>
        </form>
        <button type="button" class="btn-ghost klein b-neu" aria-expanded="false">+ von Hand</button>
      </div>
      <form class="b-form" hx-post="/api/abo/neu" hx-target="#main" hidden>
        <input type="hidden" name="typ" value="{typ}">
        <input name="name" placeholder="Anbieter" required>
        <input name="betrag" type="text" inputmode="decimal" placeholder="Betrag" style="width:6.5em" required>
        <select name="intervall" aria-label="Rhythmus">{intervall_opts("monatlich")}</select>
        <select name="kategorie_id" aria-label="Kategorie">{kat_opts(vorwahl)}</select>
        <button class="btn-primary klein">Hinzufügen</button>
        <button type="button" class="btn-ghost klein b-ab">Abbrechen</button>
      </form>
      <div class="anbieter-raster einzeln">{karten}</div>
    </section>"""

    bloecke = "".join(block(t, titel, unter) for t, titel, unter, _, _ in TYPEN)
    ruhend_html = "".join(karte(a, 0) for a in ruhend)

    # ------------------------------------------------------------ Überblick oben
    haupt = []
    for typ, titel, _, _, farbe in TYPEN:
        wert = sum(a["monatlich"] for a in aktiv if a["typ"] == typ)
        if wert:
            haupt.append({"typ": typ, "name": titel, "wert": round(wert, 2), "farbe": farbe})
    haupt_zeilen = "".join(
        f'<a class="kat-zeile" href="#block-{x["typ"]}"><span class="kat-name"><i style="background:var({x["farbe"]})"></i>{h(x["name"])}</span>'
        f'<span class="kat-balken"><span style="width:{x["wert"] / monat * 100:.1f}%;background:var({x["farbe"]})"></span></span>'
        f'<span class="kat-wert">{eur(x["wert"])}<small> · {prozent_kurz(x["wert"] / monat)}</small></span></a>' for x in haupt) if monat else ""

    groesster_kat = f'<div class="klein muted">{h(groesster["kategorie"])}</div>' if groesster else ""
    kpis = f"""
  <div class="kpis">
    <div class="kpi"><div class="l">Laufende Verträge</div><div class="w">{len(aktiv)}</div><div class="klein muted">{len(ruhend)} ruhend oder gekündigt</div></div>
    <div class="kpi"><div class="l">Pro Monat</div><div class="w">{eur(monat)}</div><div class="klein muted">{prozent_kurz(monat / ausgaben_monat) if ausgaben_monat else "–"} deiner Ausgaben</div></div>
    <div class="kpi"><div class="l">Pro Jahr</div><div class="w">{eur(monat * 12)}</div><div class="klein muted">hochgerechnet</div></div>
    <div class="kpi"><div class="l">Größter Posten</div><div class="w">{eur(groesster["monatlich"]) if groesster else "–"}</div>
      <div class="klein muted">{h(groesster["name"]) if groesster else "noch nichts erkannt"}</div>{groesster_kat}</div>
  </div>"""

    # ------------------------------------------------------------ Simulator
    daten = {"typen": [{"typ": t, "titel": titel, "kurz": kurz, "farbe": farbe} for t, titel, _, kurz, farbe in TYPEN],
             "abos": [{"partner": a["partner"], "name": a["name"], "monatlich": a["monatlich"], "typ": a["typ"],
                       "farbe": a["farbe"], "kategorie": a["kategorie"], "intervall": a["intervall"]} for a in aktiv],
             "ausgaben_monat": round(ausgaben_monat, 2), "einnahmen_monat": round(einnahmen_monat, 2)}
    daten_json = json.dumps(daten, ensure_ascii=False).replace("</", "<\\/")

    return f"""
<section class="abos">
  <div class="karte ueberblick">
    <div class="ub-koerper">
      <div class="chart-wrap rund gross"><svg id="chart-gesamt" viewBox="0 0 300 300" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Verträge nach Art"></svg><div class="tooltip" id="tip-gesamt" hidden></div></div>
      <div class="ub-rechts">
        <h3 style="margin:0 0 .1rem">Abos &amp; Verträge</h3>
        <p class="muted klein" style="margin:0 0 .3rem">Wiederkehrende Zahlungen: gleicher Empfänger, regelmäßiger Abstand, ähnlicher Betrag. Jahres- und Quartalsbeiträge sind auf den Monat umgerechnet.</p>
        <div class="kat-liste haupt-liste">{haupt_zeilen or '<p class="muted">Noch nichts erkannt – dafür braucht es mindestens drei Monate Kontoauszüge. Unten lässt sich alles von Hand eintragen.</p>'}</div>
      </div>
    </div>
  </div>
  {kpis}
  <div class="block-raster">{bloecke}</div>
  {f'<section class="v-block karte gedaempft"><header class="b-kopf"><div class="b-titel"><h3>Gekündigt, ausgelaufen oder kein Vertrag</h3><p class="muted klein">Zählt nirgends mit. Art oder Status ändern holt den Eintrag zurück.</p></div><span class="muted klein">{len(ruhend)}</span></header><div class="anbieter-raster breit">{ruhend_html}</div></section>' if ruhend else ''}
  <section class="karte spar-sim" id="spar-sim">
    <header class="b-kopf"><div class="b-titel"><h3>Was wäre, wenn …?</h3>
      <p class="muted klein">Verträge antippen, die du kündigen würdest. Geplante Mehrausgaben trägst du rechts ein.</p></div></header>
    <div class="sim-reiter" id="sim-reiter"></div>
    <div class="sim-koerper">
      <div class="sim-wahl"><div class="sim-werkzeug"><button type="button" class="btn-ghost klein" data-alle="1">alle auswählen</button><button type="button" class="btn-ghost klein" data-alle="0">Auswahl aufheben</button></div>
        <div class="abo-chips" id="abo-chips"></div></div>
      <div class="sim-ergebnis">
        <form class="neu-form" id="neu-form"><input name="name" placeholder="Mehrausgabe, z. B. Fitnessstudio" aria-label="Bezeichnung"><input name="betrag" type="number" step="0.01" min="0" placeholder="€ / Monat" aria-label="Betrag pro Monat" style="width:7.5em" required><button class="btn-secondary klein">+ Mehrausgabe</button></form>
        <div class="abo-chips" id="neu-chips"></div>
        <div class="spar-ergebnis" id="spar-ergebnis"></div>
      </div>
    </div>
  </section>
  <div class="karte chart-karte"><div class="row zwischen"><h3 style="margin:0">Entwicklung über zwölf Monate</h3><span class="muted klein">Unterschied zu heute, Monat für Monat aufsummiert: grün nach oben = gespart, rot nach unten = mehr ausgegeben</span></div>
    <div class="chart-wrap"><svg id="chart-spar" viewBox="0 0 960 340" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Entwicklung der Ersparnis"></svg><div class="tooltip" id="tip-spar" hidden></div></div>
    <div class="legende" id="leg-spar"></div></div>
  <script type="application/json" id="abo-daten">{daten_json}</script>
</section>
<script>{ABO_SKRIPT}</script>"""


def prozent_kurz(anteil: float) -> str:
    return f"{anteil * 100:.1f}".replace(".", ",").replace(",0", "") + " %"


ABO_SKRIPT = """
(function(){
  const wurzel = document.getElementById('abo-daten'); if (!wurzel) return;
  const D = JSON.parse(wurzel.textContent);
  // Überblick nach Art
  CA.donut('chart-gesamt', 'tip-gesamt', D.typen.map(t => ({name: t.titel, farbe: CA.css(t.farbe),
    wert: D.abos.filter(a => a.typ === t.typ).reduce((s, a) => s + a.monatlich, 0)})), 'pro Monat', null, {ohneLegende: true});
  // Blockweise Kreisdiagramme
  D.typen.forEach(t => {
    const teil = D.abos.filter(a => a.typ === t.typ);
    if (!teil.length) return;
    CA.donut('chart-' + t.typ, 'tip-' + t.typ, teil.map(a => ({name: a.name, wert: a.monatlich, farbe: a.farbe})), t.kurz, null, {ohneLegende: true});
  });
  // Formular je Block auf- und zuklappen
  document.querySelectorAll('.b-neu').forEach(b => b.addEventListener('click', () => {
    const f = b.closest('.v-block').querySelector('.b-form'); const auf = f.hidden;
    f.hidden = !auf; b.setAttribute('aria-expanded', auf ? 'true' : 'false'); if (auf) f.querySelector('input[name=name]').focus();
  }));
  document.querySelectorAll('.b-ab').forEach(b => b.addEventListener('click', () => {
    const f = b.closest('.b-form'); f.hidden = true; f.closest('.v-block').querySelector('.b-neu').setAttribute('aria-expanded', 'false');
  }));

  // -------- Simulator
  const weg = new Set(); let neu = []; let reiter = D.typen[0].typ;
  try { (JSON.parse(sessionStorage.getItem('abo-weg') || '[]')).forEach(p => { if (D.abos.some(a => a.partner === p)) weg.add(p); });
        neu = JSON.parse(sessionStorage.getItem('abo-neu') || '[]').filter(x => x && x.betrag > 0);
        reiter = sessionStorage.getItem('abo-reiter') || reiter; } catch(e) {}
  const merken = () => { try { sessionStorage.setItem('abo-weg', JSON.stringify([...weg])); sessionStorage.setItem('abo-neu', JSON.stringify(neu));
                               sessionStorage.setItem('abo-reiter', reiter); } catch(e) {} };
  const proz = (a, b) => b > 0 ? (a / b * 100).toLocaleString('de-DE', {maximumFractionDigits: 1}) + ' %' : '–';
  const liste = n => n.length <= 1 ? n.join('') : n.slice(0, -1).join(', ') + ' und ' + n[n.length - 1];
  const vz = x => (x > 0 ? '+' : x < 0 ? '−' : '') + CA.eur(Math.abs(x));
  const imReiter = () => D.abos.filter(a => a.typ === reiter);
  if (!imReiter().length) { const erster = D.typen.find(t => D.abos.some(a => a.typ === t.typ)); if (erster) reiter = erster.typ; }

  function zeichnen(){
    const gesamt = D.abos.reduce((s, a) => s + a.monatlich, 0);
    const spar = D.abos.filter(a => weg.has(a.partner)).reduce((s, a) => s + a.monatlich, 0);
    const mehr = neu.reduce((s, x) => s + x.betrag, 0), netto = spar - mehr, rest = gesamt - spar;
    const namen = D.abos.filter(a => weg.has(a.partner)).map(a => a.name);
    document.getElementById('sim-reiter').innerHTML = D.typen.filter(t => D.abos.some(a => a.typ === t.typ)).map(t => {
      const teil = D.abos.filter(a => a.typ === t.typ), n = teil.filter(a => weg.has(a.partner)).length;
      return `<button type="button" class="reiter ${t.typ === reiter ? 'aktiv' : ''}" data-reiter="${t.typ}">${CA.esc(t.titel)}
        <span class="z">${n ? n + '/' + teil.length : teil.length}</span></button>`;
    }).join('');
    document.getElementById('abo-chips').innerHTML = imReiter().map(a =>
      `<button type="button" class="chip ${weg.has(a.partner) ? 'aus' : ''}" data-partner="${CA.esc(a.partner)}" title="${CA.esc(a.kategorie)} · ${CA.esc(a.intervall)}">
         <span class="chip-punkt" style="background:${a.farbe}"></span><span class="chip-name">${CA.esc(a.name)}</span><span class="chip-wert">${CA.eur(a.monatlich)}</span></button>`).join('')
      || '<p class="muted klein">In diesem Bereich gibt es nichts zum Kündigen.</p>';
    document.getElementById('neu-chips').innerHTML = neu.map((x, i) =>
      `<button type="button" class="chip neu" data-i="${i}" title="entfernen"><span class="chip-name">${CA.esc(x.name || 'Mehrausgabe')}</span><span class="chip-wert">${CA.eur(x.betrag)}</span></button>`).join('');
    const erg = document.getElementById('spar-ergebnis');
    if (!D.abos.length && !neu.length) erg.innerHTML = '<p class="muted">Noch keine laufenden Verträge erkannt – dafür braucht es mindestens drei Monate Kontoauszüge.</p>';
    else if (!weg.size && !neu.length) erg.innerHTML = `<div class="gross muted">Noch nichts ausgewählt</div><p class="muted klein">Alle ${D.abos.length} Verträge zusammen kosten ${CA.eur(gesamt)} im Monat, ${CA.eur(gesamt * 12)} im Jahr – das sind ${proz(gesamt, D.ausgaben_monat)} deiner Ausgaben.</p>`;
    else {
      let html = `<div class="gross ${netto >= 0 ? 'plus' : 'minus'}">${vz(netto)} <small>im Monat</small> · ${vz(netto * 12)} <small>im Jahr</small></div>`;
      if (weg.size) html += `<p>Kündigst du ${CA.esc(liste(namen))}, sparst du <b>${CA.eur(spar)}</b> im Monat – <b>${proz(spar, gesamt)}</b> deiner Vertragskosten und <b>${proz(spar, D.ausgaben_monat)}</b> deiner monatlichen Ausgaben.</p>`;
      if (neu.length) html += `<p>Neue Ausgaben: <b class="minus">−${CA.eur(mehr)}</b> im Monat (${CA.esc(liste(neu.map(x => x.name || 'Mehrausgabe')))}).</p>`;
      html += `<p class="muted klein">Unterm Strich ${netto >= 0 ? 'bleiben dir' : 'fehlen dir'} <b>${CA.eur(Math.abs(netto))}</b> im Monat, <b>${CA.eur(Math.abs(netto) * 12)}</b> im Jahr. Es laufen dann ${D.abos.length - weg.size} Verträge mit ${CA.eur(rest)} im Monat.${D.einnahmen_monat > 0 ? ' Sparquote ' + (netto >= 0 ? '+' : '−') + proz(Math.abs(netto), D.einnahmen_monat).replace(' %', ' Punkte') + '.' : ''}</p>`;
      erg.innerHTML = html;
    }
    const labels = Array.from({length: 12}, (_, i) => String(i + 1)), f = netto >= 0 ? CA.css('--plus') : CA.css('--minus');
    CA.linien('chart-spar', 'tip-spar', 'leg-spar', labels, [
      {name: 'so wie jetzt', farbe: CA.css('--muted'), werte: labels.map(() => 0), gestrichelt: true, ohneEndwert: true},
      {name: netto >= 0 ? 'gespart' : 'mehr ausgegeben', farbe: f, werte: labels.map((_, i) => netto * (i + 1))}],
      {band: [1, 0], bandFarbe: f, bandName: 'Unterschied', einheit: n => 'nach ' + n + (n == 1 ? ' Monat' : ' Monaten'), nullLinie: true});
  }
  document.getElementById('sim-reiter').addEventListener('click', e => { const r = e.target.closest('.reiter'); if (!r) return; reiter = r.dataset.reiter; merken(); zeichnen(); });
  document.getElementById('abo-chips').addEventListener('click', e => { const c = e.target.closest('.chip'); if (!c) return; const p = c.dataset.partner;
    weg.has(p) ? weg.delete(p) : weg.add(p); merken(); zeichnen(); });
  document.getElementById('neu-chips').addEventListener('click', e => { const c = e.target.closest('.chip'); if (!c) return; neu.splice(+c.dataset.i, 1); merken(); zeichnen(); });
  document.querySelectorAll('.sim-werkzeug [data-alle]').forEach(b => b.addEventListener('click', () => {
    imReiter().forEach(a => b.dataset.alle === '1' ? weg.add(a.partner) : weg.delete(a.partner)); merken(); zeichnen(); }));
  document.getElementById('neu-form').addEventListener('submit', e => { e.preventDefault(); const f = e.target, b = parseFloat(String(f.betrag.value).replace(',', '.'));
    if (!(b > 0)) return; neu.push({name: f.name.value.trim(), betrag: Math.round(b * 100) / 100}); f.reset(); merken(); zeichnen(); });
  zeichnen();
})();
"""


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
    seite = "Einnahmen" if b.betrag > 0 else "Ausgaben"
    alle_knopf = (f'<button type="button" class="btn-ghost klein alle-knopf" hx-post="/api/bewegung/{b.id}/kategorie/alle" hx-include="closest tr, #buchungen form.filter" '
                  f'hx-target="#main" hx-swap="innerHTML" title="Diese Kategorie allen {seite} von „{h(b.gegenkonto or b.partner)}“ zuordnen – auch von Hand gesetzten">auf alle anwenden</button>')
    return (f'<tr id="bw-{b.id}" class="bw {"gespeichert" if gespeichert else ""} {"ignoriert" if b.ignoriert else ""}" data-datum="{b.datum.isoformat()}" data-betrag="{b.betrag:.2f}" '
            f'data-partner="{h((b.gegenkonto or b.partner or "").lower())} {h(b.verwendungszweck[:60].lower())}" data-kategorie="{h(k.name.lower() if k else "zzz")}" '
            f'hx-post="/api/bewegung/{b.id}/kategorie" hx-trigger="change[target.name!=\'ids\']" hx-include="closest tr" hx-target="this" hx-swap="outerHTML" hx-disinherit="*">'
            f'<td><input type="checkbox" name="ids" value="{b.id}" class="bw-wahl" aria-label="auswählen"></td>'
            f'<td class="nowrap">{d(b.datum)}<div class="klein muted">{["Mo","Di","Mi","Do","Fr","Sa","So"][b.datum.weekday()]}</div></td>'
            f'<td class="num {"plus" if b.betrag > 0 else "minus"}">{eur(b.betrag)}</td>'
            f'<td><b>{h(b.gegenkonto or "–")}</b><div class="klein muted zweck">{h(b.verwendungszweck[:120])}</div></td>'
            f'<td><span class="kat-punkt" style="background:{h(k.farbe if k else "#64748b")}"></span><select name="kategorie_id" aria-label="Kategorie">{opts}</select> {person}'
            f'<div class="klein muted zeile-fuss">{weg}{(" · " + h(hinweis)) if hinweis else ""}{(" · " + h(b.konto)) if b.konto else ""} {alle_knopf}</div></td></tr>')


def buchungen_view(zeilen: list[Bewegung], kats: dict[int, Kategorie], personen: list[str], zeitraum: str, kategorie: str, q: str, konto: str,
                   konten: list[str], nur_offen: bool, seite: str = "", zaehler: dict | None = None) -> str:
    zaehler = zaehler or {}
    reiter = "".join(f'<button type="button" class="reiter {"aktiv" if seite == w else ""}" data-seite="{w}">{t} <span class="z">{zaehler.get(w, "")}</span></button>'
                     for w, t in (("", "Alle"), ("einnahme", "Einnahmen"), ("ausgabe", "Ausgaben")))
    rows = "".join(buchung_zeile(b, kats, personen) for b in zeilen)
    kat_opts = "".join(f'<option value="{h(k.schluessel)}" {"selected" if k.schluessel == kategorie else ""}>{h(k.name)}</option>'
                       for k in sorted(kats.values(), key=lambda x: (x.art != "einnahme", x.sortierung)))
    konto_opts = "".join(f'<option value="{h(k)}" {"selected" if k == konto else ""}>{h(k)}</option>' for k in konten)
    sammel_opts = (f'<optgroup label="Ausgaben">{"".join(f"<option value={k.id}>{h(k.name)}</option>" for k in sorted(kats.values(), key=lambda x: x.sortierung) if k.art == "ausgabe")}</optgroup>'
                   f'<optgroup label="Einnahmen">{"".join(f"<option value={k.id}>{h(k.name)}</option>" for k in sorted(kats.values(), key=lambda x: x.sortierung) if k.art == "einnahme")}</optgroup>'
                   f'<optgroup label="Umbuchung">{"".join(f"<option value={k.id}>{h(k.name)}</option>" for k in kats.values() if k.art == "umbuchung")}</optgroup>')
    def hand_gruppe(titel: str, art: str, vorwahl: str) -> str:
        opts = "".join(f'<option value="{k.id}" {"selected" if k.schluessel == vorwahl else ""}>{h(k.name)}</option>' for k in sorted(kats.values(), key=lambda x: x.sortierung) if k.art == art)
        return f'<optgroup label="{titel}">{opts}</optgroup>'
    hand_opts = hand_gruppe("Einnahmen", "einnahme", "nebenerwerb") + hand_gruppe("Ausgaben", "ausgabe", "")
    ein = sum(b.betrag for b in zeilen if b.betrag > 0 and not b.ignoriert)
    aus = sum(-b.betrag for b in zeilen if b.betrag < 0 and not b.ignoriert)
    return f"""
<section class="buchungen" id="buchungen">
  <div class="reiter-leiste" id="bw-reiter">{reiter}</div>
  <form class="filter row" hx-get="/ui/buchungen" hx-target="#main" hx-trigger="change, submit, input changed delay:350ms from:input[name=q]">
    <input type="hidden" name="zeitraum" value="{h(zeitraum)}"><input type="hidden" name="seite" value="{h(seite)}">
    <input type="search" name="q" value="{h(q)}" placeholder="Suchen … (Empfänger, Zweck, Betrag)" class="suchfeld">
    <select name="kategorie"><option value="">alle Kategorien</option>{kat_opts}</select>
    {f'<select name="konto"><option value="">alle Konten</option>{konto_opts}</select>' if konten else ''}
    <label class="check"><input type="checkbox" name="nur_offen" value="1" {"checked" if nur_offen else ""}> nur unklare</label>
    <span class="muted klein">{len(zeilen)} Buchungen · <span class="plus">{eur(ein)}</span> ein · <span class="minus">{eur(aus)}</span> aus</span>
    <a class="btn-ghost klein" href="/api/export/buchungen.csv?zeitraum={h(zeitraum)}" download>CSV</a>
  </form>
  <form class="bw-aktion" hx-post="/api/bewegungen/aktion" hx-target="#main" hx-include="#buchungen .bw-wahl:checked" aria-hidden="true">
    <input type="hidden" name="zeitraum" value="{h(zeitraum)}"><input type="hidden" name="kategorie" value="{h(kategorie)}"><input type="hidden" name="q" value="{h(q)}"><input type="hidden" name="konto" value="{h(konto)}"><input type="hidden" name="nur_offen" value="{"1" if nur_offen else ""}"><input type="hidden" name="seite" value="{h(seite)}">
    <label for="bw-kat">Kategorie für die Auswahl <span class="anzahl muted"></span></label>
    <select name="kategorie_id" id="bw-kat"><option value="">– wählen –</option>{sammel_opts}</select>
    <button type="submit" name="aktion" value="kategorie" class="btn-primary klein">Anwenden</button>
    <button type="submit" name="aktion" value="ignorieren" class="btn-ghost klein" title="zählt nicht mehr mit (z. B. Kreditkartenabrechnung, die doppelt erscheint)">{ICON["auge_zu"]}ausblenden</button>
    <button type="submit" name="aktion" value="freigeben" class="btn-ghost klein">wieder einblenden</button>
    <button type="submit" name="aktion" value="loeschen" class="btn-ghost klein gefahr-text" hx-confirm="Ausgewählte Buchungen wirklich löschen?" data-confirm-vorlage="{{n}} Buchungen wirklich löschen? Ein erneuter Import desselben Auszugs bringt sie nicht zurück.">{ICON["x"]}löschen</button>
  </form>
  <div class="scroll"><table class="tabelle kompakt bw-tabelle"><colgroup><col class="c-wahl"><col class="c-datum"><col class="c-betrag"><col class="c-partner"><col class="c-kat"></colgroup>
    <thead><tr><th><input type="checkbox" class="bw-alle" aria-label="alle auswählen"></th><th class="sortierbar" data-sort="datum">Datum <span class="pfeil"></span></th><th class="num sortierbar" data-sort="betrag">Betrag <span class="pfeil"></span></th><th class="sortierbar" data-sort="partner">Empfänger / Zweck <span class="pfeil"></span></th><th class="sortierbar" data-sort="kategorie">Kategorie <span class="pfeil"></span></th></tr></thead>
    <tbody>{rows or '<tr><td colspan=5 class="muted">Keine Buchungen in dieser Auswahl.</td></tr>'}</tbody></table></div>
  <form hx-post="/api/bewegung/neu" hx-target="#main" class="hand-form karte">
    <b>Von Hand eintragen</b> <span class="muted klein">z. B. Nebenerwerb oder Bareinnahmen, die auf keinem Auszug stehen</span>
    <input type="hidden" name="zeitraum" value="{h(zeitraum)}">
    <input name="monat" type="month" required aria-label="Monat">
    <input name="betrag" type="text" inputmode="decimal" placeholder="Betrag" style="width:7em" required>
    <input name="bezeichnung" placeholder="Bezeichnung (optional)">
    <select name="kategorie_id" aria-label="Kategorie">{hand_opts}</select>
    <button class="btn-primary klein">Eintragen</button>
  </form>
  <p class="muted klein">Kategorie in der Zeile ändern speichert sofort und lernt die Zuordnung für denselben Empfänger – getrennt nach Einnahmen und Ausgaben. „Auf alle anwenden“ überschreibt auch von Hand gesetzte Buchungen dieses Empfängers auf derselben Seite. Ausgeblendete Zeilen zählen in keiner Auswertung. Sparpläne gelten als gespart, nicht als Ausgabe.</p>
</section>
<script>
(function(){{
  const box = document.getElementById('buchungen'), tbody = box.querySelector('tbody'), leiste = box.querySelector('.bw-aktion'), alle = box.querySelector('.bw-alle');
  const filter = box.querySelector('form.filter');
  box.querySelector('#bw-reiter').addEventListener('click', e => {{ const r = e.target.closest('.reiter'); if (!r) return; filter.querySelector('[name=seite]').value = r.dataset.seite; htmx.trigger(filter, 'submit'); }});
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
    const rows = [...tbody.querySelectorAll('tr.bw')]; rows.sort((a, b) => {{ const va = a.dataset[key], vb = b.dataset[key]; return (key === 'betrag' ? (+va - +vb) : key === 'datum' ? (va < vb ? -1 : va > vb ? 1 : 0) : va.localeCompare(vb, 'de')) * sortDir; }});
    rows.forEach(r => tbody.appendChild(r));
    box.querySelectorAll('th.sortierbar').forEach(t => {{ const an = t === th; t.classList.toggle('aktiv', an); t.querySelector('.pfeil').textContent = an ? (sortDir > 0 ? '▲' : '▼') : ''; }});
  }}));
}})();
</script>"""


# ---------------------------------------------------------------- Dubletten

def dubletten_view(gruppen: list[list[Bewegung]], kats: dict[int, Kategorie]) -> str:
    def zeile(b: Bewegung, erste: bool) -> str:
        k = kats.get(b.kategorie_id or -1)
        return (f'<tr class="{"behalten" if erste else ""}"><td><input type="checkbox" name="ids" value="{b.id}" class="dub-wahl" {"" if erste else "checked"} aria-label="löschen"></td>'
                f'<td class="nowrap">{d(b.datum)}</td><td class="num {"plus" if b.betrag > 0 else "minus"}">{eur(b.betrag)}</td>'
                f'<td><b>{h(b.gegenkonto or "–")}</b><div class="klein muted">{h(b.verwendungszweck[:110])}</div></td>'
                f'<td><span class="kat-punkt" style="background:{h(k.farbe if k else "#64748b")}"></span>{h(k.name if k else "–")}</td>'
                f'<td class="klein muted">{h(b.quelle_datei or "–")}{(" · " + h(b.konto)) if b.konto else ""}<div>{b.importiert_am.strftime("%d.%m.%Y %H:%M")}{" · zuerst importiert, wird behalten" if erste else ""}</div></td></tr>')

    bloecke = "".join(f'<tbody class="dub-gruppe"><tr class="dub-kopf"><td colspan="6">Gruppe {i + 1} · {len(g)} Buchungen · {h(g[0].gegenkonto or g[0].partner)} · {eur(g[0].betrag)}</td></tr>'
                      + "".join(zeile(b, j == 0) for j, b in enumerate(g)) + '</tbody>' for i, g in enumerate(gruppen))
    anzahl = sum(len(g) - 1 for g in gruppen)
    if not gruppen:
        inhalt = '<p class="ok-box"><span>Keine doppelten Einträge gefunden.</span></p>'
    else:
        inhalt = f"""
  <form hx-post="/api/dubletten/loeschen" hx-target="#main" id="dubletten-form">
    <div class="row zwischen" style="margin:.4rem 0 .8rem">
      <span class="muted">{len(gruppen)} Gruppen, {anzahl} mutmaßliche Dubletten. Vorausgewählt ist je Gruppe alles außer der zuerst importierten Buchung.</span>
      <span class="row" style="margin:0">
        <button type="submit" name="automatisch" value="1" class="btn-secondary klein" hx-confirm="Je Gruppe alle bis auf die zuerst importierte Buchung löschen? {anzahl} Buchungen werden entfernt.">Automatisch bereinigen</button>
        <button type="submit" class="btn-primary klein gefahr-knopf" hx-confirm="Ausgewählte Dubletten wirklich löschen? Ein erneuter Import bringt sie nicht zurück.">Ausgewählte löschen</button>
      </span></div>
    <div class="scroll"><table class="tabelle kompakt dub-tabelle"><thead><tr><th>löschen</th><th>Datum</th><th class="num">Betrag</th><th>Empfänger / Zweck</th><th>Kategorie</th><th>Quelle</th></tr></thead>{bloecke}</table></div>
  </form>"""
    return f"""
<section class="dubletten">
  <p class="muted erkl">Als doppelt gilt: gleicher Empfänger, gleicher Betrag, höchstens ein Tag Abstand. Das passiert, wenn derselbe Auszug als CSV und als PDF geladen wurde,
  ein Monat in zwei Auszügen steckt oder die Bank Buchungs- und Valutadatum unterschiedlich liefert. Echte Wiederholungen (zweimal derselbe Kaffee am selben Tag) sehen genauso aus – deshalb vor dem Löschen kurz draufschauen.</p>
  <div class="row"><button class="btn-ghost klein" hx-get="/ui/import" hx-target="#main">← zurück zum Import</button></div>
  {inhalt}
</section>
<script>
(function(){{ const t = document.getElementById('titel'); if (t) t.textContent = 'Doppelte Einträge';
  document.querySelectorAll('#nav button').forEach(b => b.classList.toggle('aktiv', b.dataset.ansicht === 'import')); }})();
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
  <div class="karte"><div class="row zwischen"><div><h3 style="margin:0 0 .2rem">Doppelte Einträge</h3>
    <p class="muted klein" style="margin:0">Derselbe Auszug als CSV und PDF, ein Monat zweimal geladen, Buchungs- und Valutadatum: Cash Angel findet Buchungen mit gleichem Empfänger, gleichem Betrag und höchstens einem Tag Abstand.</p></div>
    <button class="btn-secondary" hx-get="/ui/dubletten" hx-target="#main">Dubletten suchen</button></div></div>
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

def einstellungen_view(cfg: dict, kats: list[Kategorie], regeln: list[Regel], db_pfad: str, version: str, standard: set[str] | None = None) -> str:
    kat_by_id = {k.id: k for k in kats}
    standard = standard or set()
    personen = cfg.get("personen", [])

    def kat_optionen(gewaehlt: int | None, seite: str) -> str:
        gruppen = [("Ausgaben", "ausgabe"), ("Einnahmen", "einnahme"), ("Umbuchung", "umbuchung")]
        if seite == "einnahme":
            gruppen = [gruppen[1], gruppen[0], gruppen[2]]
        return "".join(f'<optgroup label="{titel}">' + "".join(f'<option value="{k.id}" {"selected" if k.id == gewaehlt else ""}>{h(k.name)}</option>'
                                                             for k in sorted(kats, key=lambda x: x.sortierung) if k.art == art) + '</optgroup>' for titel, art in gruppen)

    def regel_zeile(r: Regel) -> str:
        seite = {"einnahme": '<span class="badge ok">Einnahme</span>', "ausgabe": '<span class="badge">Ausgabe</span>'}.get(r.art, '<span class="badge mid">beide</span>')
        p_opts = "".join(f'<option value="{h(p)}" {"selected" if p == r.person else ""}>{h(p)}</option>' for p in personen)
        return (f'<tr><td><code>{h(r.muster)}</code></td><td>{seite}</td>'
                f'<td><form class="inline" hx-post="/api/regel/{r.id}" hx-target="#main" hx-trigger="change"><select name="kategorie_id" aria-label="Kategorie">{kat_optionen(r.kategorie_id, r.art)}</select> '
                f'<select name="person" aria-label="Person"><option value="">–</option>{p_opts}</select></form></td>'
                f'<td><button class="klein btn-ghost gefahr-text" hx-post="/api/regel/{r.id}/loeschen" hx-target="#main">entfernen</button></td></tr>')

    regeln_html = "".join(regel_zeile(r) for r in regeln)
    kat_defs = {d["schluessel"]: d for d in cfg.get("kategorien", [])}

    def kat_eintrag(k: Kategorie) -> str:
        muster = ", ".join(kat_defs.get(k.schluessel, {}).get("muster", [])[:12])
        eigen = k.schluessel not in standard
        knopf = (f' <button class="klein btn-ghost gefahr-text" hx-post="/api/kategorie/{h(k.schluessel)}/loeschen" hx-target="#main" '
                 f'hx-confirm="Kategorie „{h(k.name)}“ entfernen? Buchungen darin wandern nach Sonstiges.">entfernen</button>') if eigen else ""
        return (f'<li title="{h(muster)}"><input type="color" class="kat-farbe" value="{h(k.farbe)}" aria-label="Farbe für {h(k.name)}" title="Farbe ändern" '
                f'hx-post="/api/kategorie/{h(k.schluessel)}/farbe" hx-trigger="change" hx-target="#main" name="farbe" hx-disinherit="*">'
                f'<span class="kat-text">{h(k.name)} <span class="muted klein">{h(k.art)}{" · fix" if k.fix else ""}{" · eigene" if eigen else ""}</span></span>{knopf}</li>')

    kat_html = "".join(kat_eintrag(k) for k in sorted(kats, key=lambda x: (x.art != "einnahme", x.sortierung)))
    return f"""
<section class="einstellungen">
  <div class="karte"><h3 style="margin-top:0">Haushalt</h3>
    <form hx-post="/api/einstellungen" hx-target="#main" class="stapel">
      <label>Personen (für „Gehalt Susanne“, „Gehalt Dustin“) <input name="personen" value="{h(', '.join(personen))}" placeholder="Susanne, Dustin"></label>
      <label>Eigene IBANs (Umbuchungen zwischen diesen Konten zählen nicht als Einnahme/Ausgabe) <input name="eigene_ibans" value="{h(', '.join(cfg.get('eigene_ibans', [])))}" placeholder="DE12 …, DE34 …"></label>
      <label>Kleinbetrag-Grenze für den Latte-Faktor (€) <input name="kleinbetrag_grenze" type="number" step="1" value="{cfg.get('kleinbetrag_grenze', 15)}" style="width:8em"></label>
      <div><button class="btn-primary">Speichern und neu zuordnen</button></div>
    </form></div>
  <div class="karte"><h3 style="margin-top:0">Gelernte Zuordnungen ({len(regeln)})</h3>
    <p class="muted klein">Entstehen, wenn du in der Buchungsliste eine Kategorie änderst, getrennt nach Einnahmen und Ausgaben. Hier neu vergeben: Die Auswahl gilt sofort für alle Buchungen dieses Empfängers auf dieser Seite, auch künftige.</p>
    <table class="tabelle kompakt regeln-tabelle"><thead><tr><th>Empfänger</th><th>Seite</th><th>Kategorie · Person</th><th></th></tr></thead><tbody>{regeln_html or '<tr><td colspan=4 class="muted">Noch keine.</td></tr>'}</tbody></table>
    <form class="row" hx-post="/api/neu-klassifizieren" hx-target="#main" style="margin-top:.8rem">
      <button class="btn-secondary klein">Automatik erneut anwenden</button>
      <label class="check klein"><input type="checkbox" name="alle" value="1"> auch von Hand gesetzte überschreiben</label></form></div>
  <div class="karte"><h3 style="margin-top:0">Kategorien ({len(kats)})</h3>
    <form hx-post="/api/kategorie/neu" hx-target="#main" class="kat-neu">
      <input name="name" placeholder="Neue Kategorie, z. B. Solarenergie" required>
      <select name="art" aria-label="Einnahme oder Ausgabe"><option value="ausgabe">Ausgabe</option><option value="einnahme">Einnahme</option></select>
      <input name="farbe" type="color" value="#38bdf8" title="Farbe" aria-label="Farbe">
      <label class="check klein"><input type="checkbox" name="fix" value="1"> fix</label>
      <input name="muster" placeholder="Erkennungsmuster, kommagetrennt (z. B. einspeis, solar)" class="breit">
      <button class="btn-primary klein">Anlegen</button>
    </form>
    <p class="muted klein">Farbe jederzeit über das Feld links vom Namen ändern – sie gilt sofort in allen Diagrammen. Muster: Buchungen, deren Empfänger oder Zweck eines der Wörter enthält, landen automatisch in dieser Kategorie; Maus über einen Eintrag zeigt sie. Muster stehen in <code>kategorien.json</code> im Datenordner.</p>
    <ul class="kat-ul">{kat_html}</ul></div>
  <div class="karte gefahr-zone"><h3 style="margin-top:0">Daten löschen</h3>
    <p class="muted klein">Entfernt alle eingelesenen Buchungen. Kategorien und die Einstellungen oben bleiben; die Kontoauszüge kannst du danach neu einlesen.
      Doppelte Einträge findest du gezielt unter Import → „Dubletten suchen“.</p>
    <form hx-post="/api/daten/loeschen" hx-target="#main" class="row" hx-confirm="Wirklich alle Buchungen löschen? Das lässt sich nicht rückgängig machen – Sicherung ist der Ordner CashAngel im Benutzerverzeichnis.">
      <label class="check klein"><input type="checkbox" name="zuordnungen" value="1"> auch gelernte Zuordnungen und Abo-Markierungen</label>
      <label class="check klein"><input type="checkbox" name="merkliste" value="1"> auch die Merkliste gelöschter Buchungen (dann kommen sie beim nächsten Import wieder)</label>
      <button class="gefahr">Alle Buchungen löschen</button>
    </form>
    <div class="row" style="margin-top:.6rem"><span class="muted klein">Fehlt eine Buchung, die du früher gelöscht hast?</span>
      <button class="btn-secondary klein" hx-post="/api/merkliste/leeren" hx-target="#main" hx-confirm="Merkliste gelöschter Buchungen leeren? Früher gelöschte Buchungen kommen dann beim nächsten Einlesen des Auszugs wieder.">Merkliste leeren</button></div></div>
  <div class="karte"><h3 style="margin-top:0">Dateien</h3>
    <p>Datenbank: <code>{h(db_pfad)}</code><br>Version <code>{h(version)}</code> · lokal, offline, keine Telemetrie.</p>
    <div class="row"><button class="gefahr" hx-post="/api/beenden" hx-target="#main" hx-confirm="Cash Angel beenden? Der Server wird gestoppt; alle Daten sind gespeichert.">Cash Angel beenden</button></div></div>
</section>"""
