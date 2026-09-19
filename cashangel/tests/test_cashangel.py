"""Cash Angel: Kategorisierung, Abo-Erkennung, Monatsbilanz, Muster und die Oberfläche – auf einem synthetischen Jahr."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import analyse, config, ui
from app.db import engine
from app.main import app
from app.models import Bewegung, Kategorie, Regel

KOPF = "Buchungstag;Verwendungszweck;Beguenstigter/Zahlungspflichtiger;Betrag"


def zeile(d: date, zweck: str, wer: str, betrag: float) -> str:
    return f"{d.strftime('%d.%m.%Y')};{zweck};{wer};{str(betrag).replace('.', ',')}"


def jahres_csv(start: date = date(2025, 1, 1), monate: int = 12) -> str:
    """Ein Haushalt: zwei Gehälter, Miete, Strom, Netflix, Spotify, congstar, REWE/ALDI-Einkäufe, Lieferando, Amazon, Tanken, Sparplan."""
    zeilen = [KOPF]
    for i in range(monate):
        m = (start.month - 1 + i) % 12 + 1
        j = start.year + (start.month - 1 + i) // 12
        z = lambda tag: date(j, m, min(tag, 28))  # noqa: E731
        zeilen += [
            zeile(z(1), f"Gehalt {m:02d}/{j} Susanne Muster", "Firma Nord GmbH", 2900.00),
            zeile(z(1), f"Lohn/Gehalt Dustin Muster {m:02d}.{j}", "Agentur Sued AG", 3400.00),
            zeile(z(1), "Miete Musterstr. 5", "Hausverwaltung Meier", -1450.00),
            zeile(z(3), "Abschlag Strom Vertrag 4711", "Stadtwerke Giessen", -95.00),
            zeile(z(5), "Netflix.com 12345", "Netflix International", -17.99),
            zeile(z(7), "Spotify Premium", "Spotify AB", -10.99),
            zeile(z(10), "Rechnung Mobilfunk", "congstar - Telekom Deutschland GmbH", -20.00),
            zeile(z(2), "Sparplan MSCI World", "Trade Republic Bank", -300.00),
            zeile(z(4), "REWE SAGT DANKE 44112233", "REWE Markt GmbH", -round(45 + (i * 23) % 70 + 0.4, 2)),
            zeile(z(11), "ALDI SUED SAGT DANKE", "ALDI SUED", -round(30 + (i * 31) % 50 + 0.1, 2)),
            zeile(z(18), "REWE SAGT DANKE 44112233", "REWE Markt GmbH", -round(52 + (i * 19) % 60 + 0.15, 2)),
            zeile(z(25), "EDEKA Einkauf", "EDEKA Nord", -round(40 + (i * 29) % 45 + 0.3, 2)),
            zeile(z(6), "Lieferando Bestellung 998877", "Lieferando.de", -28.50),
            zeile(z(13), "Lieferando Bestellung 998878", "Lieferando.de", -31.20),
            zeile(z(20), "Wolt Order", "Wolt", -24.90),
            zeile(z(9), "AMAZON PAYMENTS 302-1234", "AMAZON EU S.A R.L.", -49.99),
            zeile(z(15), "Aral Tankstelle 1234", "ARAL AG", -70.00),
            zeile(z(8), "Coffee to go", "Starbucks Coffee", -4.80),
            zeile(z(12), "Baeckerei Schmidt", "Baeckerei Schmidt", -3.60),
            zeile(z(22), "Cafe am Markt", "Cafe am Markt", -7.20),
            zeile(z(26), "Bargeldauszahlung GA 0815", "Sparkasse", -100.00),
            zeile(z(27), "Umbuchung Tagesgeld", "Susanne Muster", -400.00),
        ]
        if m in (1, 7):
            zeilen.append(zeile(z(15), "Haftpflicht Jahresbeitrag", "HUK-COBURG Versicherung", -89.00))
    return "\n".join(zeilen) + "\n"


def client():
    return TestClient(app)


def test_kategorisierung_und_personen():
    with client() as c:
        r = c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")}, data={"konto": "Gemeinschaftskonto"})
        assert r.status_code == 200 and "neue Buchungen eingelesen" in r.text
        with Session(engine()) as s:
            kats = {k.id: k for k in s.exec(select(Kategorie)).all()}
            alle = s.exec(select(Bewegung)).all()
            nach = lambda zweck: next(b for b in alle if zweck in b.verwendungszweck)  # noqa: E731
            assert kats[nach("Gehalt 01/2025").kategorie_id].schluessel == "gehalt" and nach("Gehalt 01/2025").person == "Susanne"
            assert kats[nach("Lohn/Gehalt Dustin").kategorie_id].schluessel == "gehalt" and nach("Lohn/Gehalt Dustin").person == "Dustin"
            assert kats[nach("Miete Musterstr").kategorie_id].schluessel == "wohnen"
            assert kats[nach("Netflix.com").kategorie_id].schluessel == "abos_streaming"
            assert kats[nach("Rechnung Mobilfunk").kategorie_id].schluessel == "mobilfunk"
            assert kats[nach("REWE SAGT").kategorie_id].schluessel == "lebensmittel"
            assert kats[nach("Lieferando Bestellung 998877").kategorie_id].schluessel == "restaurants"
            assert kats[nach("Sparplan").kategorie_id].schluessel == "sparen"
            assert kats[nach("Umbuchung Tagesgeld").kategorie_id].schluessel == "umbuchung"
            assert kats[nach("Bargeldauszahlung").kategorie_id].schluessel == "bargeld"
            assert kats[nach("Haftpflicht").kategorie_id].schluessel == "versicherungen"
        # Doppelimport bringt nichts Neues
        r = c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")})
        assert "0 neue Buchungen" in r.text


def test_abos_und_monatsbilanz():
    with client() as c:
        c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")})
        with Session(engine()) as s:
            kats = {k.id: k for k in s.exec(select(Kategorie)).all()}
            alle = s.exec(select(Bewegung)).all()
            abos = analyse.abos_finden(alle, kats, date(2025, 12, 28))
            nach = {a["partner"]: a for a in abos}
            netflix = next(a for a in abos if "netflix" in a["partner"])
            assert netflix["intervall"] == "monatlich" and netflix["monatlich"] == 17.99 and netflix["aktiv"] and netflix["art"] == "Abo"
            huk = next(a for a in abos if "huk" in a["partner"])
            assert huk["intervall"] == "halbjährlich" and huk["monatlich"] == round(89 / 6, 2)
            assert any("hausverwaltung" in p for p in nach) and any("stadtwerke" in p for p in nach)
            assert not any("rewe" in p for p in nach)          # Einkäufe sind unregelmäßig im Betrag/Abstand
            bilanz = analyse.monatsbilanz(alle, kats, analyse.monate_im_zeitraum("jahr:2025"))
            jan = bilanz["monate"][0]
            assert jan["einnahmen"] == 6300.0 and jan["personen"] == {"Gehalt Susanne": 2900.0, "Gehalt Dustin": 3400.0}
            assert jan["ausgaben"] > 2000 and "umbuchung" not in jan["kategorien"]
            assert jan["fix"] >= 1450 + 95 + 17.99 + 10.99 + 20 + 89 and jan["gespart"] == 300.0 and "sparen" not in jan["kategorien"]
            assert not any("sparkasse" in p or "susanne" in p for p in nach)   # Bargeld und Umbuchung sind keine Abos
            assert bilanz["summe"]["sparquote"] is not None and 0 < bilanz["summe"]["sparquote"] < 100
            ins = analyse.insights(alle, kats, analyse.monate_im_zeitraum("jahr:2025"), abos, config.konfig())
            titel = " ".join(k["titel"] for k in ins["karten"])
            assert "Sparquote" in titel and "Abos" in titel and "Latte-Faktor" in titel and "Lieferdienste" in titel
            assert len(ins["wochentage"]) == 7 and ins["top_summe"][0]["name"].startswith("Hausverwaltung")


def test_oberflaeche_und_lernen():
    with client() as c:
        assert "Cash Angel" in c.get("/").text
        assert "Willkommen" in c.get("/ui/uebersicht").text
        c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")})
        s_ = c.get("/api/status").json()
        assert s_["bewegungen"] > 200 and any(z["wert"] == "jahr:2025" for z in s_["zeitraeume"])
        u = c.get("/api/uebersicht?zeitraum=jahr:2025").json()
        assert u["summe"]["einnahmen"] == 12 * 6300 and u["abos"]["anzahl"] >= 5
        assert {q["name"] for q in u["einnahmequellen"]} == {"Gehalt Susanne", "Gehalt Dustin"}
        for pfad in ("/ui/uebersicht?zeitraum=jahr:2025", "/ui/abos", "/ui/buchungen?zeitraum=jahr:2025", "/ui/muster?zeitraum=jahr:2025", "/ui/import", "/ui/einstellungen"):
            assert c.get(pfad).status_code == 200, pfad
        t = c.get("/ui/buchungen?zeitraum=jahr:2025&q=starbucks").text
        assert "Starbucks" in t and t.count('class="bw ') == 12
        # Kategorie ändern → Regel gelernt, alle Starbucks-Buchungen ziehen nach
        with Session(engine()) as s:
            b = s.exec(select(Bewegung).where(Bewegung.gegenkonto == "Starbucks Coffee")).first()
            freizeit = s.exec(select(Kategorie).where(Kategorie.schluessel == "freizeit")).first()
            bid, fid = b.id, freizeit.id
        r = c.post(f"/api/bewegung/{bid}/kategorie", data={"kategorie_id": str(fid), "person": "", "lernen": "1"})
        assert "+11 gleiche" in r.text
        with Session(engine()) as s:
            assert all(x.kategorie_id == fid for x in s.exec(select(Bewegung).where(Bewegung.gegenkonto == "Starbucks Coffee")).all())
            assert s.exec(select(Regel).where(Regel.muster == "starbucks coffee")).first() is not None
        # Sammelaktion ausblenden + löschen
        with Session(engine()) as s:
            ids = [x.id for x in s.exec(select(Bewegung).where(Bewegung.gegenkonto == "Wolt")).all()]
        r = c.post("/api/bewegungen/aktion", data={"aktion": "ignorieren", "ids": [str(i) for i in ids[:2]], "zeitraum": "jahr:2025"})
        assert "2 ausgeblendet" in r.text
        r = c.post("/api/bewegungen/aktion", data={"aktion": "loeschen", "ids": [str(ids[2])], "zeitraum": "jahr:2025"})
        assert "1 gelöscht" in r.text
        r = c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")})
        assert "0 neue Buchungen" in r.text   # gelöschte kommt nicht zurück
        # Abo-Status
        r = c.post("/api/abo/status", data={"partner": "netflix international", "status": "gekuendigt"})
        assert "gekündigt" in r.text
        assert c.get("/api/uebersicht?zeitraum=jahr:2025").json()["abos"]["monatlich"] < u["abos"]["monatlich"]
        # Einstellungen: Personen ändern
        r = c.post("/api/einstellungen", data={"personen": "Susi, Dustin", "eigene_ibans": "", "kleinbetrag_grenze": "10"})
        assert "Gespeichert" in r.text and config.konfig()["personen"] == ["Susi", "Dustin"]
        assert "text/csv" in c.get("/api/export/buchungen.csv?zeitraum=jahr:2025").headers["content-type"]


def test_zeitraeume_und_partner():
    assert analyse.monate_im_zeitraum("3m", date(2025, 2, 10)) == ["2024-12", "2025-01", "2025-02"]
    assert analyse.monate_im_zeitraum("monat:2025-09") == ["2025-09"]
    assert analyse.monate_im_zeitraum("jahr:2025")[0] == "2025-01" and len(analyse.monate_im_zeitraum("jahr:2025")) == 12
    assert analyse.partner_schluessel("REWE SAGT DANKE 44112233", "") == "rewe sagt danke"
    assert analyse.partner_schluessel("Netflix International", "") == "netflix international"
    assert analyse.partner_schluessel("PayPal: Spotify AB", "") == "spotify"
    assert analyse.partner_schluessel("", "Lieferando Bestellung 998877") == "lieferando bestellung"


ING_TEXT = """Girokonto Nummer 5411382540
Kontoauszug Juli 2025
Buchung Buchung / Verwendungszweck Betrag (EUR)
Valuta
01.07.2025 Lastschrift PayPal Europe S.a.r.l. et Cie S.C.A -237,70
01.07.2025 1043156212407/PP.6087.PP/., Ihr Einkauf bei
Mandat: 5VE2224PVQYLG
Referenz: 1043156212407
02.07.2025 Gutschrift/Dauerauftrag Anneliese Nicolai 600,00
02.07.2025 Miete und Nebenkosten
03.07.2025 Lastschrift Susanne und Dustin Nicolai -1.095,07
03.07.2025 Teilzahlung Darlehen RECHN.ZINS 431,89 TILG./ENTG. 663,18
TILGUNG PER 01.07.2025
Mandat: 0209499478D500105175411382540
10.07.2025 Dauerauftrag/Terminueberw. Norbert und Ulrike Zoerb -501,21
10.07.2025 Rate
10.07.2025 Lastschrift PayPal Europe S.a.r.l. et Cie S.C.A -17,99
10.07.2025 1043381785725/PP.9417.PP/. Spotify AB, Ihr Einkauf bei Spotify AB
Seite 1 von 2
30.07.2025 Gehalt/Rente NAHKETING GMBH 1.491,42
30.07.2025 Lohn - Gehalt Abrechnung 07/2025
01.07.2025 Lastschrift congstar - eine Marke der Telekom D eutschland -17,50
01.07.2025 GmbH
congstar Kundennummer 2210831760 Rechnung 1445099246
"""


def test_ing_pdf_text_kombinierte_typen():
    from app.kontoauszug import lese_pdf_text
    bs = lese_pdf_text(ING_TEXT)
    assert [round(b.betrag, 2) for b in bs] == [-237.70, 600.00, -1095.07, -501.21, -17.99, 1491.42, -17.50]
    assert round(sum(b.betrag for b in bs), 2) == 221.95
    # PayPal ohne erkennbaren Händler bleibt PayPal, „Mandat:“ wird nicht zum Händler
    assert bs[0].gegenkonto == "PayPal Europe S.a.r.l. et Cie S.C.A"
    assert bs[4].gegenkonto == "PayPal: Spotify AB"
    # Typ wandert in den Zweck, damit Gehalt/Dauerauftrag erkannt werden
    assert bs[1].verwendungszweck.startswith("Dauerauftrag Miete")  # „Gutschrift“ bleibt draußen
    assert bs[5].verwendungszweck.startswith("Gehalt/Rente Lohn")
    assert bs[3].gegenkonto == "Norbert und Ulrike Zoerb"
    # Beträge im Zweck (Zins/Tilgung) sind keine eigenen Buchungen
    assert "431,89" in bs[2].verwendungszweck
    # Spaltenumbruch im Namen repariert
    assert bs[6].gegenkonto == "congstar - eine Marke der Telekom Deutschland"


def test_eigene_kategorien_regeln_und_auf_alle_anwenden():
    with client() as c:
        c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")})
        # Solarenergie ist als Einnahme-Kategorie da; Amazon-Gutschrift (Einnahme) und Amazon-Kauf (Ausgabe) sind getrennt
        t = c.get("/ui/einstellungen").text
        assert "Solarenergie" in t
        # eigene Kategorie anlegen
        r = c.post("/api/kategorie/neu", data={"name": "Vereinsbeiträge", "art": "ausgabe", "fix": "1", "farbe": "#ff8800", "muster": "verein, tsv"})
        assert "angelegt (vereinsbeitraege)" in r.text
        with Session(engine()) as s:
            k = s.exec(select(Kategorie).where(Kategorie.schluessel == "vereinsbeitraege")).first()
            assert k and k.art == "ausgabe" and k.fix and k.farbe == "#ff8800"
            kid = k.id
            # Standardkategorie lässt sich nicht entfernen
        assert "nicht entfernen" in c.post("/api/kategorie/lebensmittel/loeschen").text
        # „Auf alle anwenden“: Starbucks-Ausgaben bekommen die neue Kategorie, auch eine vorher von Hand gesetzte
        with Session(engine()) as s:
            sb = s.exec(select(Bewegung).where(Bewegung.gegenkonto == "Starbucks Coffee")).all()
            erste, zweite = sb[0].id, sb[1].id
            freizeit = s.exec(select(Kategorie).where(Kategorie.schluessel == "freizeit")).first().id
        c.post(f"/api/bewegung/{erste}/kategorie", data={"kategorie_id": str(freizeit), "person": "", "lernen": "0"})
        r = c.post(f"/api/bewegung/{zweite}/kategorie/alle", data={"kategorie_id": str(kid), "person": "", "zeitraum": "jahr:2025"})
        assert "gilt jetzt für alle 12 Ausgaben von Starbucks Coffee, 11 davon geändert" in r.text
        with Session(engine()) as s:
            assert all(x.kategorie_id == kid for x in s.exec(select(Bewegung).where(Bewegung.gegenkonto == "Starbucks Coffee")).all())
            regel = s.exec(select(Regel).where(Regel.muster == "starbucks coffee")).first()
            assert regel.art == "ausgabe" and regel.kategorie_id == kid
            rid = regel.id
            # Regel gilt nur für Ausgaben: eine Einnahme von Starbucks bleibt Einnahme-Kategorie
            kats = {k.schluessel: k for k in s.exec(select(Kategorie)).all()}
            gut = Bewegung(datum=date(2025, 6, 1), betrag=5.0, verwendungszweck="Erstattung", gegenkonto="Starbucks Coffee", partner="starbucks coffee")
            kk, _, _ = analyse.klassifiziere(gut, kats, [regel], config.konfig())
            assert kk.art == "einnahme"
        # Zuordnung in den Einstellungen neu vergeben
        with Session(engine()) as s:
            restaurants = s.exec(select(Kategorie).where(Kategorie.schluessel == "restaurants")).first().id
        r = c.post(f"/api/regel/{rid}", data={"kategorie_id": str(restaurants), "person": ""})
        assert "Zuordnung geändert" in r.text
        with Session(engine()) as s:
            assert all(x.kategorie_id == restaurants for x in s.exec(select(Bewegung).where(Bewegung.gegenkonto == "Starbucks Coffee")).all())
        # eigene Kategorie entfernen
        r = c.post("/api/kategorie/vereinsbeitraege/loeschen")
        assert "entfernt" in r.text and "vereinsbeitraege" not in {d["schluessel"] for d in config.konfig()["kategorien"]}
        # Sortierköpfe in der Buchungsliste
        t = c.get("/ui/buchungen?zeitraum=jahr:2025&q=starbucks").text
        assert 'data-sort="partner"' in t and 'data-sort="kategorie"' in t and "auf alle anwenden" in t


def test_dubletten_und_alles_loeschen():
    with client() as c:
        c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")})
        vorher = c.get("/api/status").json()["bewegungen"]
        assert "Keine doppelten Einträge" in c.get("/ui/dubletten").text
        # derselbe Auszug nochmal, aber mit anderem Zweck-Text (wie CSV vs. PDF) → alles doppelt
        nochmal = jahres_csv().replace(";Netflix", " Abo;Netflix").replace(";Spotify", " Abo;Spotify")
        r = c.post("/api/import", files={"datei": ("konto-pdf.csv", nochmal.encode(), "text/csv")})
        assert "24 neue Buchungen" in r.text
        t = c.get("/ui/dubletten").text
        assert "24 Gruppen, 24 mutmaßliche Dubletten" in t and "wird behalten" in t
        with Session(engine()) as s:
            gruppen = analyse.dubletten(s.exec(select(Bewegung)).all())
            assert len(gruppen) == 24 and all(g[0].quelle_datei == "konto.csv" for g in gruppen)
            eine = gruppen[0][1].id
        r = c.post("/api/dubletten/loeschen", data={"ids": [str(eine)]})
        assert "1 doppelte Buchungen gelöscht" in r.text
        r = c.post("/api/dubletten/loeschen", data={"automatisch": "1"})
        assert "23 doppelte Buchungen gelöscht" in r.text
        assert c.get("/api/status").json()["bewegungen"] == vorher
        assert "0 neue Buchungen" in c.post("/api/import", files={"datei": ("konto-pdf.csv", nochmal.encode(), "text/csv")}).text
        # alles löschen
        r = c.post("/api/daten/loeschen", data={"zuordnungen": "1"})
        assert f"{vorher} Buchungen gelöscht" in r.text and "Abo-Markierungen entfernt" in r.text
        assert c.get("/api/status").json()["bewegungen"] == 0
        assert "Willkommen" in c.get("/ui/uebersicht").text


def test_abos_bearbeiten_handeintraege_und_reiter():
    with client() as c:
        c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")})
        vorher = c.get("/api/uebersicht?zeitraum=jahr:2025").json()["abos"]
        # erkanntes Abo umbenennen und Monatsbetrag anpassen
        r = c.post("/api/abo/bearbeiten", data={"partner": "netflix international", "name": "Netflix Familie", "monatlich": "19,99", "kategorie_id": "", "status": "ok"})
        assert "Netflix Familie" in r.text and 'value="19,99"' in r.text
        # Abo von Hand
        r = c.post("/api/abo/neu", data={"name": "Fitnessstudio", "betrag": "29,90", "intervall": "monatlich", "kategorie_id": ""})
        assert "Fitnessstudio" in r.text and "von Hand ·" in r.text
        r = c.post("/api/abo/neu", data={"name": "Haftpflicht", "betrag": "120", "intervall": "jaehrlich", "kategorie_id": ""})
        assert "Haftpflicht" in r.text
        nachher = c.get("/api/uebersicht?zeitraum=jahr:2025").json()["abos"]
        assert nachher["anzahl"] == vorher["anzahl"] + 2
        assert abs(nachher["monatlich"] - (vorher["monatlich"] - 17.99 + 19.99 + 29.90 + 10.0)) < 0.02
        with Session(engine()) as s:
            from app.models import AboManuell
            mid = s.exec(select(AboManuell).where(AboManuell.name == "Haftpflicht")).first().id
        r = c.post("/api/abo/bearbeiten", data={"partner": f"manuell:{mid}", "name": "Haftpflicht", "betrag": "240", "intervall": "jaehrlich", "kategorie_id": "", "status": "ok"})
        assert "20,00" in r.text
        assert "Haftpflicht" not in c.post(f"/api/abo/manuell/{mid}/loeschen").text
        # Einnahme von Hand: Nebenerwerb im März
        with Session(engine()) as s:
            neben = s.exec(select(Kategorie).where(Kategorie.schluessel == "nebenerwerb")).first().id
        r = c.post("/api/bewegung/neu", data={"monat": "2025-03", "betrag": "350", "bezeichnung": "Fotoauftrag", "kategorie_id": str(neben), "zeitraum": "jahr:2025"})
        assert "Fotoauftrag: 350,00 € für Mär 2025 eingetragen" in r.text
        u = c.get("/api/uebersicht?zeitraum=jahr:2025").json()
        assert any(q["name"] == "Nebenerwerb" and q["wert"] == 350 for q in u["einnahmequellen"])
        assert "Solarenergie" in c.get("/ui/buchungen?zeitraum=jahr:2025").text
        # Reiter Einnahmen | Ausgaben
        t = c.get("/ui/buchungen?zeitraum=jahr:2025&seite=einnahme").text
        assert t.count('class="bw ') == 25 and 'data-seite="einnahme">Einnahmen' in t
        t = c.get("/ui/buchungen?zeitraum=jahr:2025&seite=ausgabe&q=starbucks").text
        assert t.count('class="bw ') == 12
        # Merkliste leeren bringt Gelöschtes zurück
        with Session(engine()) as s:
            bid = s.exec(select(Bewegung).where(Bewegung.gegenkonto == "Wolt")).first().id
        c.post("/api/bewegungen/aktion", data={"aktion": "loeschen", "ids": [str(bid)], "zeitraum": "jahr:2025"})
        assert "0 neue" in c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")}).text
        assert "Merkliste geleert" in c.post("/api/merkliste/leeren").text
        assert "1 neue" in c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")}).text


def test_typ_flags_und_kategoriefarbe():
    with client() as c:
        c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")})
        t = c.get("/ui/abos").text
        # HUK-COBURG steckt in „Versicherungen“ und landet damit im Block Versicherung & Krankenkasse
        assert 'id="block-krankenkasse"' in t and 'id="block-depot"' in t and 'id="block-kredit"' in t
        vorher = c.get("/api/uebersicht?zeitraum=jahr:2025").json()["abos"]
        # Netflix von „Abo“ auf „Vertrag“ umflaggen
        r = c.post("/api/abo/bearbeiten", data={"partner": "netflix international", "name": "Netflix", "monatlich": "17,99",
                                                "kategorie_id": "", "status": "ok", "typ": "vertrag"})
        assert "Netflix" in r.text
        with Session(engine()) as s:
            from app.models import AboStatus
            assert s.exec(select(AboStatus).where(AboStatus.partner == "netflix international")).first().typ == "vertrag"
        # als „kein Vertrag“ flaggen: fällt aus Summe und Simulator, taucht unten auf
        r = c.post("/api/abo/bearbeiten", data={"partner": "netflix international", "name": "Netflix", "monatlich": "17,99",
                                                "kategorie_id": "", "status": "ok", "typ": "kein"})
        assert "kein Vertrag" in r.text
        nachher = c.get("/api/uebersicht?zeitraum=jahr:2025").json()["abos"]
        assert nachher["anzahl"] == vorher["anzahl"] - 1 and abs(nachher["monatlich"] - (vorher["monatlich"] - 17.99)) < 0.02
        # Kategoriefarbe ändern wirkt sofort in der Konfiguration und in den Diagrammen
        r = c.post("/api/kategorie/lebensmittel/farbe", data={"farbe": "#ff8800"})
        assert "Farbe für „Lebensmittel“ geändert" in r.text
        assert next(d for d in config.konfig()["kategorien"] if d["schluessel"] == "lebensmittel")["farbe"] == "#ff8800"
        assert any(k["schluessel"] == "lebensmittel" and k["farbe"] == "#ff8800"
                   for k in c.get("/api/uebersicht?zeitraum=jahr:2025").json()["kategorien"])
        assert "#ff8800" in c.get("/ui/einstellungen").text
        # Gehalt je Person bekommt denselben Ton, die zweite Person heller
        quellen = c.get("/api/uebersicht?zeitraum=jahr:2025").json()["einnahmequellen"]
        gehalt = [q for q in quellen if q["name"].startswith("Gehalt ")]
        assert len(gehalt) == 2 and gehalt[0]["farbe"] != gehalt[1]["farbe"] and all(q["farbe"].startswith("#") for q in gehalt)


def test_aus_zuordnungen_uebernehmen():
    with client() as c:
        c.post("/api/import", files={"datei": ("konto.csv", jahres_csv().encode(), "text/csv")})
        t = c.get("/ui/abos").text
        # Überblick oben, Kennzahlen darunter, Boxen je Art
        assert 'id="chart-gesamt"' in t and 'class="kpis"' in t and 'class="block-raster"' in t
        assert t.index('id="chart-gesamt"') < t.index('class="kpis"') < t.index('class="block-raster"')
        # ALDI SUED taucht als Vorschlag auf, ist aber noch kein Vertrag
        assert "ALDI SUED" in t and t.count('<option value="aldi sued"') == len(ui.TYPEN)
        r = c.post("/api/abo/aus-zuordnung", data={"partner": "aldi sued", "typ": "vertrag"})
        assert "ALDI SUED" in r.text and '<option value="aldi sued"' not in r.text   # jetzt Vertrag, nicht mehr Vorschlag
        with Session(engine()) as s:
            from app.models import AboManuell
            m = s.exec(select(AboManuell).where(AboManuell.quelle_partner == "aldi sued")).first()
            assert m and m.typ == "vertrag" and m.betrag > 0 and m.intervall == "monatlich"
        # zählt jetzt in den Summen mit
        assert c.get("/api/uebersicht?zeitraum=jahr:2025").json()["abos"]["anzahl"] >= 6
