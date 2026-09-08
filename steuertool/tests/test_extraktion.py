from datetime import date

from app.importer import zugferd
from app.importer.textfelder import extrahiere_felder, finde_ust_idnr, parse_betrag, parse_datum
from tests.fixtures import erzeuge


def test_parse_betrag_formate():
    assert parse_betrag("1.234,56") == 1234.56
    assert parse_betrag("1,234.56") == 1234.56
    assert parse_betrag("59,49") == 59.49
    assert parse_betrag("1234.5") == 1234.5
    assert parse_betrag("12,-") == 12.0
    assert parse_betrag("-99,78") == -99.78
    assert parse_betrag("1.500") == 1500.0


def test_parse_datum_formate():
    assert parse_datum("Rechnungsdatum: 05.02.2025") == date(2025, 2, 5)
    assert parse_datum("2025-03-14") == date(2025, 3, 14)
    assert parse_datum("12. März 2025") == date(2025, 3, 12)
    assert parse_datum("March 12, 2025") == date(2025, 3, 12)
    assert parse_datum("kein datum") is None


def test_ust_idnr():
    assert finde_ust_idnr("USt-IdNr. DE987654321 und VAT ID: IE6364992H") == ["DE987654321", "IE6364992H"]


def test_adobe_text_reverse_charge(cfg):
    f = extrahiere_felder(erzeuge.ADOBE_TEXT, cfg)
    assert f["datum"] == date(2025, 2, 5)
    assert f["betrag_brutto"] == 59.49
    assert f["ust_idnr"] == "IE6364992H"
    assert f["rechnungsnummer"] == "INV1234567890"
    assert f["reverse_charge_hinweis"] is True
    assert f["ust_satz"] == 0.0
    assert "adobe" in f["lieferant"].lower()


def test_buero_text_deutsch(cfg):
    f = extrahiere_felder(erzeuge.BUERO_TEXT, cfg)
    assert f["datum"] == date(2025, 3, 21)
    assert f["betrag_brutto"] == 99.78
    assert f["betrag_netto"] == 83.85
    assert f["ust_satz"] == 19.0 and f["ust_betrag"] == 15.93
    assert f["ust_idnr"] == "DE987654321"
    assert f["rechnungsnummer"] == "2025-1187"
    assert "Meier GmbH" in f["lieferant"]


def test_zugferd_xml_direkt():
    f = zugferd.parse_xml(erzeuge.ZUGFERD_XML)
    assert f["rechnungsnummer"] == "RE-2025-0042" and f["datum"] == date(2025, 3, 14)
    assert f["lieferant"] == "Papier & Stift GmbH" and f["ust_idnr"] == "DE123456789"
    assert (f["betrag_netto"], f["ust_betrag"], f["betrag_brutto"], f["ust_satz"]) == (100.0, 19.0, 119.0, 19.0)
    assert f["reverse_charge_hinweis"] is False


def test_zugferd_aus_pdf_anhang():
    pdf = erzeuge.zugferd_pdf()
    f = zugferd.lese_erechnung(pdf)
    assert f and f["xml_datei"] == "factur-x.xml" and f["betrag_brutto"] == 119.0


def test_ubl_xrechnung():
    ubl = b"""<?xml version="1.0"?><Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
      xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
      xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
      <cbc:ID>X-1</cbc:ID><cbc:IssueDate>2025-04-02</cbc:IssueDate><cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
      <cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>Figma Inc.</cbc:Name></cac:PartyName>
        <cac:PartyTaxScheme><cbc:CompanyID>EU372009975</cbc:CompanyID></cac:PartyTaxScheme></cac:Party></cac:AccountingSupplierParty>
      <cac:TaxTotal><cbc:TaxAmount>0</cbc:TaxAmount><cac:TaxSubtotal><cac:TaxCategory><cbc:ID>AE</cbc:ID><cbc:Percent>0</cbc:Percent></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
      <cac:LegalMonetaryTotal><cbc:TaxExclusiveAmount>15.00</cbc:TaxExclusiveAmount><cbc:TaxInclusiveAmount>15.00</cbc:TaxInclusiveAmount></cac:LegalMonetaryTotal>
    </Invoice>"""
    f = zugferd.parse_xml(ubl)
    assert f["format"] == "ubl" and f["lieferant"] == "Figma Inc." and f["reverse_charge_hinweis"] and f["betrag_brutto"] == 15.0


def test_steuernummer_ist_kein_betrag(cfg):
    text = """Adobe Systems Software Ireland Ltd
Kunde: Designstudio Test
Steuernummer: 114.103.475,00
Kundennummer 114103475
VAT ID: IE6364992H
Invoice Number: IE1234567
Invoice Date: 28-FEB-2025
Creative Cloud All Apps        EUR 71.38
Total (EUR)                    71.38
"""
    # Die „Steuernummer“-Zeile trägt zwar Nachkommastellen, aber „Total“ ist ein Schlüsselwort und gewinnt
    f = extrahiere_felder(text, cfg)
    assert f["betrag_brutto"] == 71.38
    text2 = "Steuernummer 114.103.475\nTelefon 030 123 456 78\nSumme 59,49 €\n"
    assert extrahiere_felder(text2, cfg)["betrag_brutto"] == 59.49
    text3 = "Rechnungsnummer 114.103.475\nirgendwas ohne Betrag\n"
    assert extrahiere_felder(text3, cfg)["betrag_brutto"] is None


ADOBE_DE_TEXT = """Adobe Systems Software Ireland Ltd ORIGINAL Rechnungsinformationen
4-6 Riverwalk Rechnungsnummer IEN2025000321887
Citywest Business Campus Rechnungsdatum 02-JAN-2025
Dublin 24 Zahlungsfrist Paypal
Ireland Kundenauftragsnumm AE02647100001CDE
USt-IdNr.: DE813296628 Bestellnummer 7168780931
Kundennummer 562114456
Währung EUR
Rechnungsanschrift
Dustin Nicolai
GERMANY
Rechnung
Positionen
Laufzeit: 02-JAN-2025 bis 01-FEB-2025
PRODUKTNUMMER PRODUKTBESCHREIBUNG MENGE EINHEIT EINZELPREIS SUMME NETTO UST-SATZ UST SUMME BRUTTO
65206874 Creative Cloud (alle Applikationen) 1 EA 77.49 77.49 19.00% 14.72 92.21
GESAMT
SUMME NETTO (EUR) 77.49
UST (STEUERSATZ SIEHE OBEN) 14.72
USt
GESAMTBETRAG (EUR) 92.21
Anmerkungen:
http://www.adobe.com/support/service/
VAT
Ansprechpartner
https://helpx.adobe.com/contact.html
Vielen Dank für Ihre Bestellung! Seite 1 von 1
"""


def test_adobe_deutsche_rechnung_mit_ust(cfg):
    f = extrahiere_felder(ADOBE_DE_TEXT, cfg)
    assert f["datum"] == date(2025, 1, 2)
    assert f["betrag_brutto"] == 92.21 and f["betrag_netto"] == 77.49
    assert f["ust_satz"] == 19.0 and f["ust_betrag"] == 14.72
    assert f["ust_idnr"] == "DE813296628" and "ANSPRECHPARTNER" not in f["alle_ust_idnr"]
    assert f["rechnungsnummer"] == "IEN2025000321887"
    assert f["lieferant"].startswith("Adobe Systems Software Ireland Ltd")
    assert f["reverse_charge_hinweis"] is False
