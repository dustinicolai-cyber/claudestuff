from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.main import app
from app.models import Anlagegut, Beleg, Buchung, Kategorie, Regel
from tests.fixtures import erzeuge


def client():
    return TestClient(app)


def test_startseite_und_status():
    with client() as c:
        assert "Steuerfuchs" in c.get("/").text
        assert c.get("/static/htmx.min.js").status_code == 200
        s = c.get("/api/status").json()
        assert s["vorschlaege"] == 0 and isinstance(s["jahre"], list)
        for pfad in ("/ui/import", "/ui/pruefen", "/ui/quartale", "/ui/auswertung", "/ui/offen", "/ui/jahresabschluss", "/ui/export", "/ui/manuell", "/ui/einstellungen"):
            r = c.get(pfad)
            assert r.status_code == 200, pfad


def test_import_pruefen_bestaetigen_gwg_wird_afa():
    with client() as c:
        r = c.post("/api/import", files={"datei": ("adobe.pdf", erzeuge.text_pdf(erzeuge.ADOBE_TEXT), "application/pdf")}, data={"ki": "0"})
        assert "neu" in r.text and "PDF-Text" in r.text
        assert c.get("/api/status").json()["vorschlaege"] == 1
        pr = c.get("/ui/pruefen")
        assert "Adobe" in pr.text and "§13b" in pr.text and "buchung-form" in pr.text and "Ausgaben" in pr.text

        with Session(engine()) as s:
            b = s.exec(select(Buchung)).first()
            gwg = s.exec(select(Kategorie).where(Kategorie.schluessel == "gwg")).first()
            software = s.exec(select(Kategorie).where(Kategorie.schluessel == "software")).first()
            bid = b.id
        # Korrektur auf Software → Regel entsteht, Status bestätigt
        r = c.post(f"/api/buchung/{bid}/bestaetigen", data={
            "datum": "2025-02-05", "richtung": "ausgabe", "lieferant": "Adobe Systems Software Ireland Ltd", "beschreibung": "CC",
            "betrag_netto": "59.49", "ust_satz": "0", "ust_betrag": "0", "betrag_brutto": "59.49", "kategorie_id": str(software.id), "reverse_charge": "1"})
        assert r.status_code == 200 and "Keine offenen Ausgaben" in r.text
        with Session(engine()) as s:
            b = s.get(Buchung, bid)
            assert b.status == "bestaetigt" and b.eur_zeile == 50 and b.konfidenz == 1.0
            assert s.exec(select(Regel).where(Regel.muster == "adobe systems")).first() is not None

        # Manuelle Buchung über GWG-Grenze → Anlagegut
        r = c.post("/api/buchung/neu", data={"datum": "2025-10-01", "richtung": "ausgabe", "lieferant": "Apple", "beschreibung": "MacBook",
                                             "betrag_brutto": "3600", "ust_satz": "19", "kategorie_id": str(gwg.id), "meta_nutzungsdauer_jahre": "3"})
        assert r.status_code == 200
        with Session(engine()) as s:
            a = s.exec(select(Anlagegut)).first()
            assert a and a.anschaffungskosten == 3600.0 and a.nutzungsdauer_jahre == 3
            mb = s.exec(select(Buchung).where(Buchung.lieferant == "Apple")).first()
            kat = s.get(Kategorie, mb.kategorie_id)
            assert kat.schluessel == "anlagevermoegen" and mb.eur_zeile is None

        q = c.get("/ui/quartale?jahr=2025&modus=ust")
        assert "11,30" in q.text            # §13b-Steuer als entgangene Vorsteuer
        assert "300,00" in q.text           # AfA 2025: 3 Monate
        eur = c.get("/export/eur.json?jahr=2025").json()["zeilen"]
        z = {e["zeile"]: e["betrag"] for e in eur if e["zeile"]}
        assert z[50] == 59.49 and z[48] == 11.3 and z[30] == 300.0
        u = c.get("/export/ustva/2025/1").json()
        assert u["kennzahlen"] == {"46": 59.49, "47": 11.3}
        assert c.get("/export/quartale.pdf?jahr=2025").content.startswith(b"%PDF")
        assert c.get("/export/eur.pdf?jahr=2025").content.startswith(b"%PDF")
        assert "Adobe" in c.get("/export/belegjournal.csv?jahr=2025").text
        assert "Kategorie;" in c.get("/export/quartale.csv?jahr=2025").text


def test_kontoauszug_und_offene_punkte():
    with client() as c:
        r = c.post("/api/konto/import", files={"datei": ("umsaetze.csv", erzeuge.CSV_SPARKASSE.encode(), "text/csv")})
        assert "4 neue Kontobewegungen" in r.text
        o = c.get("/ui/offen")
        assert "Netflix" in o.text and "Kunde Muster AG" in o.text
        # Buchung aus Kontobewegung anlegen → landet im Prüfen als Vorschlag
        from sqlmodel import Session
        from app.models import Kontobewegung
        with Session(engine()) as s:
            k = s.exec(select(Kontobewegung).where(Kontobewegung.betrag == 1500.0)).first()
        r = c.post(f"/api/konto/{k.id}/buchung-anlegen")
        assert "buchung-form" in r.text and "Kunde Muster AG" in r.text
        with Session(engine()) as s:
            b = s.exec(select(Buchung)).first()
            assert b.richtung == "einnahme" and b.status == "vorschlag" and b.extraktion_stufe == "kontoauszug"


def test_jahresabschluss_direkterfassung():
    with client() as c:
        with Session(engine()) as s:
            ho = s.exec(select(Kategorie).where(Kategorie.schluessel == "arbeitszimmer")).first()
        r = c.post("/api/buchung/neu", data={"datum": "2025-12-31", "richtung": "ausgabe", "kategorie_id": str(ho.id), "betrag_brutto": "",
                                             "ust_satz": "0", "meta_tage": "120", "zurueck": "jahresabschluss:2025"})
        assert "Jahresabschluss 2025" in r.text
        z = {e["zeile"]: e["betrag"] for e in c.get("/export/eur.json?jahr=2025").json()["zeilen"] if e["zeile"]}
        assert z[54] == 720.0
        r = c.post("/api/fragebogen/2025/homeoffice/toggle")
        assert "1/" in r.text


def test_auswertung_daten():
    with client() as c:
        with Session(engine()) as s:
            k = {x.schluessel: x for x in s.exec(select(Kategorie)).all()}
            s.add(Buchung(datum=date(2025, 2, 1), richtung="einnahme", betrag_netto=1000, betrag_brutto=1000, kategorie_id=k["einnahmen"].id, status="bestaetigt"))
            s.add(Buchung(datum=date(2025, 8, 9), richtung="ausgabe", betrag_netto=84.03, ust_satz=19, ust_betrag=15.97, betrag_brutto=100, kategorie_id=k["bewirtung"].id, status="bestaetigt"))
            s.commit()
        d = c.get("/api/auswertung?jahr=2025").json()
        assert d["quartale"][0]["einnahmen"] == 1000.0 and d["quartale"][2]["ausgaben"] == 70.0
        assert d["monate"][1]["gewinn_kumuliert"] == 1000.0 and d["monate"][11]["gewinn_kumuliert"] == 930.0
        assert d["monate"][7]["ust"] == 15.97
        assert [k["name"] for k in d["kategorien"] if k["richtung"] == "ausgabe"] == ["Bewirtung"]
        assert d["jahr_summe"]["gewinn"] == 930.0


def test_sammel_loeschen_mit_papierkorb(tmp_path):
    from pathlib import Path
    from app import config
    with client() as c:
        for name in ("a.pdf", "b.pdf"):
            c.post("/api/import", files={"datei": (name, erzeuge.text_pdf(erzeuge.ADOBE_TEXT.replace("INV1234567890", name)), "application/pdf")}, data={"ki": "0"})
        with Session(engine()) as s:
            ids = [b.id for b in s.exec(select(Buchung)).all()]
            pfade = [Path(x.dateipfad) for x in s.exec(select(Beleg)).all()]
        assert len(ids) == 2 and all(p.exists() for p in pfade)
        r = c.post("/api/buchungen/loeschen", data={"ids": [str(i) for i in ids]})
        assert "2 Buchungen gelöscht" in r.text
        with Session(engine()) as s:
            assert s.exec(select(Buchung)).all() == [] and s.exec(select(Beleg)).all() == []
        assert all(not p.exists() for p in pfade)
        assert len(list((config.beleg_dir() / "Papierkorb").iterdir())) == 2
        # erneuter Import ist kein Duplikat mehr
        r = c.post("/api/import", files={"datei": ("a.pdf", erzeuge.text_pdf(erzeuge.ADOBE_TEXT.replace("INV1234567890", "a.pdf")), "application/pdf")}, data={"ki": "0"})
        assert ">neu<" in r.text


def test_neu_erkennen_aktualisiert_vorschlag():
    with client() as c:
        c.post("/api/import", files={"datei": ("buero.pdf", erzeuge.text_pdf(erzeuge.BUERO_TEXT), "application/pdf")}, data={"ki": "0"})
        with Session(engine()) as s:
            b = s.exec(select(Buchung)).first()
            b.betrag_brutto = 999999.0; b.lieferant = "kaputt"; s.add(b); s.commit(); bid = b.id
        r = c.post(f"/api/buchung/{bid}/neu-erkennen")
        assert r.status_code == 200
        with Session(engine()) as s:
            b = s.get(Buchung, bid)
            assert b.betrag_brutto == 99.78 and "Meier" in b.lieferant
        r = c.post("/api/buchungen/neu-erkennen", data={"ids": [str(bid)]})
        assert "1 von 1" in r.text


def test_import_einnahme_und_reiter():
    with client() as c:
        r = c.post("/api/import", files={"datei": ("re.pdf", erzeuge.zugferd_pdf(), "application/pdf")}, data={"ki": "0", "richtung": "einnahme"})
        assert "Einnahme" in r.text
        with Session(engine()) as s:
            b = s.exec(select(Buchung)).first()
            kat = s.get(Kategorie, b.kategorie_id)
            assert b.richtung == "einnahme" and kat.schluessel == "einnahmen" and b.reverse_charge is False
            assert b.lieferant == "Designstudio Test"   # Käufer aus der E-Rechnung
        assert "Keine offenen Ausgaben" in c.get("/ui/pruefen?richtung=ausgabe").text
        r = c.get("/ui/pruefen?richtung=einnahme")
        assert "buchung-form" in r.text and "Designstudio Test" in r.text
        assert "buchung-form" in c.get("/ui/pruefen").text   # ohne Reiter: springt zum Reiter mit Vorschlägen
