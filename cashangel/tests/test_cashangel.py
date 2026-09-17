"""Cash Angel: Kategorisierung, Abo-Erkennung, Monatsbilanz, Muster und die Oberfläche – auf einem synthetischen Jahr."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import analyse, config
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
