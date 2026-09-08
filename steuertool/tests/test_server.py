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
        assert z[50] == 59.49 and z[30] == 300.0 and 48 not in z  # Zeile 48 erst mit Zahlung ans Finanzamt (Abfluss)
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
        assert "Fragen geprüft" in r.text and "jahresabschluss" in r.text
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


def test_offene_punkte_aktionen_und_status():
    with client() as c:
        with Session(engine()) as s:
            k = {x.schluessel: x for x in s.exec(select(Kategorie)).all()}
            for i in range(2):   # zwei identische bestätigte Buchungen → Doppelbuchung
                s.add(Buchung(datum=date(2025, 3, 1), lieferant="Adobe", rechnungsnummer="X-1", betrag_netto=50, betrag_brutto=59.5,
                              kategorie_id=k["software"].id, eur_zeile=50, status="bestaetigt"))
            s.add(Buchung(datum=date(2025, 4, 1), lieferant="Bar-Kauf", betrag_netto=10, betrag_brutto=11.9,
                          kategorie_id=k["buerobedarf"].id, eur_zeile=50, status="bestaetigt"))
            s.commit()
            ids = [b.id for b in s.exec(select(Buchung).order_by(Buchung.id)).all()]
        st = c.get("/api/status?jahr=2025").json()
        assert st["offen_gesamt"] == 4 and st["jahresabschluss"]["gesamt"] == 13 and st["ki"] in ("aktiv", "aus", "nicht_erreichbar")
        o = c.get("/ui/offen")
        assert "Zusammenführen" in o.text and "Privat verauslagt" in o.text and "Alle Kontobewegungen haben einen Beleg." in o.text
        # privat verauslagt
        r = c.post("/api/ohnekonto/aktion", data={"aktion": "privat", "ids": [str(ids[2])]})
        assert "1 als privat verauslagt" in r.text
        # stornieren einer bestätigten Buchung: bleibt, zählt nicht mehr
        r = c.post("/api/ohnekonto/aktion", data={"aktion": "stornieren", "ids": [str(ids[2])]})
        with Session(engine()) as s:
            b = s.get(Buchung, ids[2]); assert b is not None and b.storniert
        z = {e["zeile"]: e["betrag"] for e in c.get("/export/eur.json?jahr=2025").json()["zeilen"] if e["zeile"]}
        assert z[50] == 119.0   # 2 × 59,50, die stornierte 11,90 fehlt
        # zusammenführen: ältere ID bleibt
        r = c.post("/api/doppel/zusammenfuehren", data={"paare": [f"{ids[0]}-{ids[1]}"]})
        assert "1 Paare zusammengeführt" in r.text
        with Session(engine()) as s:
            assert s.get(Buchung, ids[0]) is not None and s.get(Buchung, ids[1]) is None
            from app.models import Protokoll
            assert any(p.aktion == "zusammengefuehrt" for p in s.exec(select(Protokoll)).all())
        assert "Protokoll" in c.get("/export/belegjournal.csv?jahr=2025").text
        assert c.get("/api/status?jahr=2025").json()["offen_gesamt"] == 1   # nur noch eine ohne Kontobewegung


def test_doppel_sind_unterschiedlich():
    with client() as c:
        with Session(engine()) as s:
            for i in range(2):
                s.add(Buchung(datum=date(2025, 3, 1), lieferant="Hoster", rechnungsnummer="H-1", betrag_netto=10, betrag_brutto=11.9, status="bestaetigt"))
            s.commit()
            ids = [b.id for b in s.exec(select(Buchung)).all()]
        r = c.post("/api/doppel/unterschiedlich", data={"paare": [f"{ids[0]}-{ids[1]}"]})
        assert "1 Paare als geprüft" in r.text and "Keine Auffälligkeiten." in r.text


def test_abgleich_rueckfrage_ignorregel_doppelt():
    with client() as c:
        # Rechnung mit 59,49 am 05.02. – Kontobewegung am 06.02. matcht automatisch; zweite gleiche Bewegung ist „evtl. doppelt“
        c.post("/api/import", files={"datei": ("adobe.pdf", erzeuge.text_pdf(erzeuge.ADOBE_TEXT), "application/pdf")}, data={"ki": "0"})
        csv = erzeuge.CSV_SPARKASSE + "DE00123;07.02.2025;07.02.2025;KARTENZAHLUNG;ADOBE SYSTEMS DUBLIN;Adobe Systems Software Ireland;IE00;XXX;-59,49;EUR;Umsatz gebucht\n"
        r = c.post("/api/konto/import", files={"datei": ("umsaetze.csv", csv.encode(), "text/csv")})
        assert "5 neue Kontobewegungen" in r.text and "Kontoauszug einlesen" in r.text
        a = c.get("/ui/abgleich?jahr=2025&filter=alle").text
        assert "zugeordnet" in a and "kein Beleg" in a and "evtl. doppelt" in a and "Netflix" in a
        # Regel: netflix immer ignorieren
        r = c.post("/api/ignorregel/neu", data={"muster": "netflix", "jahr": "2025"})
        assert "1 Kontobewegungen ignoriert" in r.text
        from app.models import Kontobewegung
        with Session(engine()) as s:
            k = s.exec(select(Kontobewegung).where(Kontobewegung.gegenkonto == "Netflix International")).first()
            assert k.ignoriert
            einnahme = s.exec(select(Kontobewegung).where(Kontobewegung.betrag == 1500.0)).first()
        # Buchung aus Einnahme anlegen → Vorschlag unter Prüfen (Einnahmen)
        r = c.post("/api/abgleich/aktion", data={"aktion": "anlegen", "ids": [str(einnahme.id)], "jahr": "2025", "filter": "alle"})
        assert "1 Buchungsvorschläge" in r.text
        assert 'class="aktiv" hx-get="/ui/abgleich?filter=alle"' in r.text  # Reiter bleibt erhalten
        assert 'name="filter" value="alle"' in r.text
        with Session(engine()) as s:
            b = s.exec(select(Buchung).where(Buchung.richtung == "einnahme")).first()
            assert b and b.status == "vorschlag" and b.betrag_brutto == 1500.0
        assert c.get("/api/status?jahr=2025").json()["vorschlaege"] == 2


def test_beschreibung_stift_im_kopf():
    with client() as c:
        c.post("/api/import", files={"datei": ("adobe.pdf", erzeuge.text_pdf(erzeuge.ADOBE_TEXT), "application/pdf")}, data={"ki": "0"})
        t = c.get("/ui/pruefen").text
        assert "kopf-beschreibung" in t and 'name="beschreibung"' in t and t.count('name="beschreibung"') == 1


def test_abgleich_beleg_hochladen_und_pdf_auszug():
    from tests.fixtures.rechnungen import ING_AUSZUG
    from app.export import MiniPdf
    with client() as c:
        pdf = MiniPdf(quer=False)
        for z in ING_AUSZUG.splitlines():
            pdf.zeile([(40, z, False)], groesse=9, hoehe=12)
        r = c.post("/api/konto/import", files={"datei": ("Kontoauszug.pdf", pdf.bytes(), "application/pdf")})
        assert "10 neue Kontobewegungen" in r.text
        from app.models import Kontobewegung
        with Session(engine()) as s:
            k = s.exec(select(Kontobewegung).where(Kontobewegung.betrag == -92.21)).first()
            assert k is not None
        # Rechnung (92,21) direkt an die Kontobewegung hängen
        from tests.test_extraktion import ADOBE_DE_TEXT
        r = c.post(f"/api/abgleich/{k.id}/beleg", files={"datei": ("adobe.pdf", erzeuge.text_pdf(ADOBE_DE_TEXT), "application/pdf")}, data={"jahr": "2025"})
        assert r.status_code == 200 and "weicht" not in r.text
        with Session(engine()) as s:
            k = s.get(Kontobewegung, k.id); b = s.get(Buchung, k.buchung_id)
            assert b is not None and b.betrag_brutto == 92.21 and b.richtung == "ausgabe"


def test_suche_und_kunden_umsatz():
    with client() as c:
        with Session(engine()) as s:
            k = {x.schluessel: x for x in s.exec(select(Kategorie)).all()}
            s.add(Buchung(datum=date(2025, 2, 1), richtung="einnahme", lieferant="Kunde Muster AG", beschreibung="Logo", rechnungsnummer="RE-7", betrag_netto=1500, betrag_brutto=1500, kategorie_id=k["einnahmen"].id, status="bestaetigt"))
            s.add(Buchung(datum=date(2025, 3, 1), richtung="einnahme", lieferant="Zweiter Kunde", betrag_netto=500, betrag_brutto=500, kategorie_id=k["einnahmen"].id, status="bestaetigt"))
            s.add(Buchung(datum=date(2025, 3, 5), richtung="ausgabe", lieferant="Adobe", betrag_netto=50, betrag_brutto=59.5, kategorie_id=k["software"].id, status="vorschlag"))
            s.commit()
        assert "Kunde Muster AG" in c.get("/ui/suche?q=muster").text
        assert "1 Treffer" in c.get("/ui/suche?q=RE-7").text
        assert "1 Treffer" in c.get("/ui/suche?q=59,50").text        # Betragssuche
        assert "2 Treffer" in c.get("/ui/suche?q=Kunde").text
        d = c.get("/api/auswertung?jahr=2025").json()
        assert d["kunden"] == [{"name": "Kunde Muster AG", "betrag": 1500.0}, {"name": "Zweiter Kunde", "betrag": 500.0}]


def test_usd_rechnung_euro_aus_kontoauszug():
    from app.importer import textfelder
    from app.models import Kontobewegung
    usd = """Figma, Inc.
760 Market St, San Francisco, CA
Invoice number FIG-1
Invoice date 15-JAN-2025
Professional plan            $15.00
Subtotal                     $15.00
Tax                          $0.00
Total                        $15.00
Reverse charge: VAT to be accounted for by the recipient.
"""
    assert textfelder.erkenne_waehrung(usd) == "USD"
    with client() as c:
        r = c.post("/api/import", files={"datei": ("figma.pdf", erzeuge.text_pdf(usd), "application/pdf")}, data={"ki": "0"})
        with Session(engine()) as s:
            b = s.exec(select(Buchung)).first()
            assert b.waehrung == "USD" and b.betrag_fremd == 15.0 and b.betrag_brutto == 15.0 and b.reverse_charge
        # Kontoauszug: 15 $ wurden als 14,20 € abgebucht → passt per Kurstoleranz, Euro-Betrag wird übernommen
        csv = "Buchungstag;Betrag;Verwendungszweck;Beguenstigter/Zahlungspflichtiger\n17.01.2025;-14,20;FIGMA MONTHLY;VISA FIGMA\n"
        r = c.post("/api/konto/import", files={"datei": ("k.csv", csv.encode(), "text/csv")})
        assert "1 automatisch" in r.text
        with Session(engine()) as s:
            b = s.exec(select(Buchung)).first(); k = s.exec(select(Kontobewegung)).first()
            assert k.buchung_id == b.id and b.betrag_brutto == 14.2 and b.betrag_netto == 14.2 and b.betrag_fremd == 15.0
        # Formular: Währung wechseln und Fremdbetrag speichern
        with Session(engine()) as s:
            kat = s.exec(select(Kategorie).where(Kategorie.schluessel == "software")).first()
        r = c.post(f"/api/buchung/{b.id}/bestaetigen", data={"datum": "2025-01-15", "richtung": "ausgabe", "lieferant": "Figma", "betrag_netto": "14.20",
                                                            "ust_satz": "0", "ust_betrag": "0", "betrag_brutto": "14.20", "kategorie_id": str(kat.id),
                                                            "reverse_charge": "1", "waehrung": "USD", "betrag_fremd": "15"})
        assert r.status_code == 200
        with Session(engine()) as s:
            b = s.get(Buchung, b.id); assert b.status == "bestaetigt" and b.waehrung == "USD" and b.betrag_fremd == 15.0
        assert "USD 15,00" in c.get("/export/belegjournal.csv?jahr=2025").text
        a = c.get("/ui/abgleich?jahr=2025&filter=alle").text
        assert 'data-sort="betrag"' in a and 'data-sort="status"' in a and "listen-suche" in a
        assert 'data-status="3"' in a  # zugeordnete Bewegung trägt ihren Sortier-Rang


def test_rueckfragen_gesammelt_zuordnen():
    """Betrag passt, Datum 15 Tage daneben → Rückfrage; Sammelaktion ordnet die nächste Rechnung zu."""
    with client() as c:
        c.post("/api/import", files={"datei": ("adobe.pdf", erzeuge.text_pdf(erzeuge.ADOBE_TEXT), "application/pdf")}, data={"ki": "0"})
        kopf = erzeuge.CSV_SPARKASSE.splitlines()[0]
        csv = kopf + "\nDE00123;20.02.2025;20.02.2025;KARTENZAHLUNG;ADOBE SPAET;Adobe Systems Software Ireland;IE00;XXX;-59,49;EUR;Umsatz gebucht\n"
        c.post("/api/konto/import", files={"datei": ("umsaetze.csv", csv.encode(), "text/csv")})
        a = c.get("/ui/abgleich?jahr=2025&filter=rueckfrage").text
        assert "Rückfrage" in a and 'data-status="0"' in a and "Rückfragen zuordnen" in a
        from app.models import Kontobewegung
        with Session(engine()) as s:
            k = s.exec(select(Kontobewegung).where(Kontobewegung.verwendungszweck == "ADOBE SPAET")).first()
            assert k and not k.buchung_id
        r = c.post("/api/abgleich/aktion", data={"aktion": "zuordnen", "ids": [str(k.id)], "jahr": "2025", "filter": "rueckfrage"})
        assert "1 Rückfragen zugeordnet" in r.text
        with Session(engine()) as s:
            k = s.get(Kontobewegung, k.id)
            assert k.buchung_id and s.get(Buchung, k.buchung_id).betrag_brutto == 59.49


def test_bestaetigte_korrigieren():
    """Eingecheckte Buchung erscheint in der Liste „Bestätigte Buchungen“ und lässt sich in derselben Maske korrigieren."""
    with client() as c:
        c.post("/api/import", files={"datei": ("adobe.pdf", erzeuge.text_pdf(erzeuge.ADOBE_TEXT), "application/pdf")}, data={"ki": "0"})
        with Session(engine()) as s:
            b = s.exec(select(Buchung)).first()
            kat = s.exec(select(Kategorie).where(Kategorie.schluessel == "software")).first()
        daten = {"datum": "2025-02-05", "richtung": "ausgabe", "lieferant": "Adobe", "betrag_netto": "59.49", "ust_satz": "0", "ust_betrag": "0",
                 "betrag_brutto": "59.49", "kategorie_id": str(kat.id), "waehrung": "EUR", "betrag_fremd": "0"}
        c.post(f"/api/buchung/{b.id}/bestaetigen", data=daten)
        t = c.get("/ui/pruefen").text
        assert "Bestätigte Buchungen" in t and f'hx-get="/ui/pruefen/{b.id}"' in t
        t = c.get(f"/ui/pruefen/{b.id}").text
        assert "Korrektur speichern" in t and 'class="badge ok">bestätigt' in t and "Überspringen" not in t
        r = c.post(f"/api/buchung/{b.id}/bestaetigen", data={**daten, "lieferant": "Adobe Systems (korrigiert)", "betrag_brutto": "60.00", "betrag_netto": "60.00"})
        assert "Korrektur gespeichert" in r.text and "Adobe Systems (korrigiert)" in r.text
        with Session(engine()) as s:
            b = s.get(Buchung, b.id)
            assert b.status == "bestaetigt" and b.betrag_brutto == 60.0 and b.lieferant == "Adobe Systems (korrigiert)"


def test_schnell_korrektur_in_tabelle():
    """Inline-Änderung in der Tabelle bestätigter Buchungen: Zeile kommt aktualisiert zurück, Beträge werden nachgerechnet."""
    with client() as c:
        c.post("/api/import", files={"datei": ("adobe.pdf", erzeuge.text_pdf(erzeuge.ADOBE_TEXT), "application/pdf")}, data={"ki": "0"})
        with Session(engine()) as s:
            b = s.exec(select(Buchung)).first()
            kat = s.exec(select(Kategorie).where(Kategorie.schluessel == "software")).first()
        c.post(f"/api/buchung/{b.id}/bestaetigen", data={"datum": "2025-02-05", "richtung": "ausgabe", "lieferant": "Adobe", "betrag_netto": "50", "ust_satz": "19",
                                                        "ust_betrag": "9.5", "betrag_brutto": "59.5", "kategorie_id": str(kat.id), "waehrung": "EUR", "betrag_fremd": "0"})
        t = c.get("/ui/pruefen?jahr=2025").text
        assert 'class="tabelle kompakt bz-tabelle"' in t and f'hx-post="/api/buchung/{b.id}/schnell"' in t and 'class="kombi"' in t and 'data-liste="lieferanten"' in t and '<datalist id="lieferanten">' in t and 'hx-disinherit="*"' in t
        r = c.post(f"/api/buchung/{b.id}/schnell", data={"datum": "2025-02-07", "lieferant": "Adobe Inc.", "beschreibung": "Creative Cloud", "kategorie_id": str(kat.id), "betrag_brutto": "119.00"})
        assert r.status_code == 200 and 'class="bz gespeichert"' in r.text and 'value="Adobe Inc."' in r.text
        with Session(engine()) as s:
            b = s.get(Buchung, b.id)
            assert b.betrag_brutto == 119.0 and b.betrag_netto == 100.0 and b.ust_betrag == 19.0 and b.beschreibung == "Creative Cloud" and b.datum.isoformat() == "2025-02-07"
            assert b.status == "bestaetigt"
        # Vorschlagsliste enthält den neuen Namen alphabetisch
        assert 'option value="Adobe Inc."' in c.get("/ui/manuell").text


def test_finanzamt_aus_kontoauszug_und_rueckbuchung():
    """Überweisung ans Finanzamt wird als USt-Zahlung erkannt (Zeile 48); Zahlung + Storno werden als Rückbuchungspaar markiert."""
    with client() as c:
        kopf = erzeuge.CSV_SPARKASSE.splitlines()[0]
        csv = kopf + ("\nDE00123;10.04.2025;10.04.2025;UEBERWEISUNG;STEUERNR 039/852 UMS.ST 1.VJ 25;Finanzamt Giessen;DE12;XXX;-72,82;EUR;Umsatz gebucht"
                      "\nDE00123;12.05.2025;12.05.2025;LASTSCHRIFT;Abo Mai;Zeitschrift XY;DE13;XXX;-29,90;EUR;Umsatz gebucht"
                      "\nDE00123;14.05.2025;14.05.2025;RUECKBUCHUNG;Storno Abo Mai;Zeitschrift XY;DE13;XXX;29,90;EUR;Umsatz gebucht\n")
        c.post("/api/konto/import", files={"datei": ("umsaetze.csv", csv.encode(), "text/csv")})
        a = c.get("/ui/abgleich?jahr=2025&filter=alle").text
        assert "Umsatzsteuer ans Finanzamt gezahlt" in a          # Vorschlag in der Abgleich-Spalte
        assert a.count("Rückbuchung</span>") == 2 and "beide ignorieren" in a
        from app.models import Kontobewegung
        with Session(engine()) as s:
            fa = s.exec(select(Kontobewegung).where(Kontobewegung.gegenkonto == "Finanzamt Giessen")).first()
            paar = [k.id for k in s.exec(select(Kontobewegung).where(Kontobewegung.gegenkonto == "Zeitschrift XY")).all()]
        # Paar mit einer Aktion ignorieren (ids mit Komma)
        r = c.post("/api/abgleich/aktion", data={"aktion": "ignorieren", "ids": [",".join(map(str, paar))], "jahr": "2025", "filter": "alle"})
        assert "2 ignoriert" in r.text
        # Finanzamt-Zahlung ohne Beleg buchen → Kategorie ust_zahlung, kein USt-Anteil
        c.post("/api/abgleich/aktion", data={"aktion": "anlegen", "ids": [str(fa.id)], "jahr": "2025"})
        with Session(engine()) as s:
            b = s.exec(select(Buchung).where(Buchung.lieferant == "Finanzamt Giessen")).first()
            kat = s.get(Kategorie, b.kategorie_id)
            assert kat.schluessel == "ust_zahlung" and b.ust_betrag == 0 and b.betrag_netto == 72.82 and b.klassifizierung_weg == "finanzamt"
        # bestätigen → Zeile 48 = 72,82 (Abflussprinzip), Hinweiskasten in den Quartalen
        c.post(f"/api/buchung/{b.id}/bestaetigen", data={"datum": "2025-04-10", "richtung": "ausgabe", "lieferant": "Finanzamt Giessen", "betrag_netto": "72.82",
                                                        "ust_satz": "0", "ust_betrag": "0", "betrag_brutto": "72.82", "kategorie_id": str(kat.id), "waehrung": "EUR", "betrag_fremd": "0"})
        z = {e["zeile"]: e["betrag"] for e in c.get("/export/eur.json?jahr=2025").json()["zeilen"] if e["zeile"]}
        assert z[48] == 72.82
        q = c.get("/ui/quartale?jahr=2025").text
        assert "ans Finanzamt gezahlt" in q and "72,82" in q
        # Umschalten auf „rechnung“: Zahlung zählt nicht mehr, Einstellung wird gespeichert
        r = c.post("/api/einstellungen/ust-basis", data={"basis": "rechnung"})
        assert "§13b-Steuer je Rechnung" in r.text
        z = {e["zeile"]: e["betrag"] for e in c.get("/export/eur.json?jahr=2025").json()["zeilen"] if e["zeile"]}
        assert 48 not in z
        c.post("/api/einstellungen/ust-basis", data={"basis": "zahlung"})
