from datetime import date

from sqlmodel import select

from app import matching, regeln
from app.importer import kontoauszug, pipeline
from app.models import Anlagegut, Buchung, Kontobewegung, Regel
from tests.fixtures import erzeuge


def test_zugferd_import_konfidenz_1(session):
    erg = pipeline.importiere_datei(session, erzeuge.zugferd_pdf(), "re-42.pdf", ki_erlaubt=False)
    assert erg.status == "neu" and erg.stufe == "zugferd"
    b = session.get(Buchung, erg.buchung_id)
    assert b.status == "vorschlag" and b.betrag_brutto == 119.0 and b.lieferant == "Papier & Stift GmbH"
    assert b.extraktion_stufe == "zugferd" and b.datum == date(2025, 3, 14)
    # Duplikat über SHA-256
    dup = pipeline.importiere_datei(session, erzeuge.zugferd_pdf(), "nochmal.pdf", ki_erlaubt=False)
    assert dup.status == "duplikat" and dup.buchung_id == erg.buchung_id


def test_pdf_text_import_reverse_charge(session):
    erg = pipeline.importiere_datei(session, erzeuge.text_pdf(erzeuge.ADOBE_TEXT), "adobe.pdf", ki_erlaubt=False)
    assert erg.stufe == "pdf"
    b = session.get(Buchung, erg.buchung_id)
    assert b.reverse_charge is True and b.betrag_brutto == 59.49 and b.betrag_netto == 59.49 and b.ust_idnr == "IE6364992H"
    assert b.klassifizierung_weg == "fallback"  # keine Regel, keine KI


def test_regel_greift_vor_ki(session, kats):
    session.add(Regel(muster="adobe", kategorie_id=kats["software"].id, prioritaet=10))
    session.commit()
    erg = pipeline.importiere_datei(session, erzeuge.text_pdf(erzeuge.ADOBE_TEXT), "adobe.pdf", ki_erlaubt=False)
    b = session.get(Buchung, erg.buchung_id)
    assert b.kategorie_id == kats["software"].id and b.klassifizierung_weg.startswith("regel:")


def test_regel_aus_korrektur(session, kats):
    r = regeln.regel_aus_korrektur(session, "Adobe Systems Software Ireland Ltd", kats["software"].id)
    assert r.muster == "adobe systems" and r.erstellt_aus_korrektur
    assert regeln.passende_regel(session, "ADOBE SYSTEMS DUBLIN").id == r.id
    # zweite Korrektur zieht dieselbe Regel um
    r2 = regeln.regel_aus_korrektur(session, "Adobe Systems", kats["werbekosten"].id)
    assert r2.id == r.id and r2.kategorie_id == kats["werbekosten"].id


def test_csv_sparkasse():
    bew = kontoauszug.lese_csv(erzeuge.CSV_SPARKASSE.encode("utf-8"))
    assert len(bew) == 4
    assert bew[0].datum == date(2025, 2, 6) and bew[0].betrag == -59.49 and "Adobe" in bew[0].gegenkonto
    assert bew[2].betrag == 1500.0


def test_csv_soll_haben_spalten():
    csv = "Datum,Beschreibung,Soll,Haben\n2025-05-01,Miete Atelier,\"450.00\",\n2025-05-03,Honorar,,\"800.00\"\n"
    bew = kontoauszug.lese_csv(csv.encode())
    assert [b.betrag for b in bew] == [-450.0, 800.0]


def test_camt053():
    bew = kontoauszug.lese_camt053(erzeuge.CAMT053)
    assert len(bew) == 2 and bew[0].betrag == -59.49 and bew[0].gegenkonto == "Adobe Systems Software Ireland"
    assert bew[1].betrag == 1500.0 and bew[1].gegenkonto == "Kunde Muster AG"


def test_matching_betrag_exakt_datum_toleranz(session, kats):
    pipeline.importiere_datei(session, erzeuge.text_pdf(erzeuge.ADOBE_TEXT), "adobe.pdf", ki_erlaubt=False)   # 05.02., 59,49
    pipeline.importiere_datei(session, erzeuge.text_pdf(erzeuge.BUERO_TEXT), "buero.pdf", ki_erlaubt=False)   # 21.03., 99,78
    bew = kontoauszug.lese_csv(erzeuge.CSV_SPARKASSE.encode())
    neu, dup = matching.kontobewegungen_speichern(session, bew, "test.csv")
    assert (neu, dup) == (4, 0)
    assert matching.kontobewegungen_speichern(session, bew, "test.csv") == (0, 4)
    treffer = matching.matche(session)
    assert treffer == 2
    op = matching.offene_punkte(session)
    offen = {k.gegenkonto for k in op["ohne_beleg"]}
    assert offen == {"Kunde Muster AG", "Netflix International"}
    assert op["ohne_konto"] == []


def test_matching_ausserhalb_toleranz(session, kats):
    session.add(Buchung(datum=date(2025, 1, 1), richtung="ausgabe", betrag_brutto=10.0, betrag_netto=10.0))
    session.add(Kontobewegung(datum=date(2025, 1, 20), betrag=-10.0, fingerprint="x"))
    session.commit()
    assert matching.matche(session) == 0


def test_doppelbuchung_erkannt(session):
    for _ in range(2):
        session.add(Buchung(datum=date(2025, 1, 1), lieferant="Hoster", betrag_brutto=12.0, betrag_netto=10.08, rechnungsnummer="H-1"))
    session.commit()
    assert len(matching.offene_punkte(session)["doppel"]) == 1
