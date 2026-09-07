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
