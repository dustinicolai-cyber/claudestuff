"""Erzeugt Test-PDFs programmatisch: ein ZUGFeRD-PDF (XML-Anhang) und ein Text-PDF."""
from __future__ import annotations

import io

from pypdf import PdfWriter

from app.export import MiniPdf

ZUGFERD_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
 xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
 xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
 <rsm:ExchangedDocument><ram:ID>RE-2025-0042</ram:ID><ram:TypeCode>380</ram:TypeCode>
  <ram:IssueDateTime><udt:DateTimeString format="102">20250314</udt:DateTimeString></ram:IssueDateTime></rsm:ExchangedDocument>
 <rsm:SupplyChainTradeTransaction>
  <ram:ApplicableHeaderTradeAgreement>
   <ram:SellerTradeParty><ram:Name>Papier &amp; Stift GmbH</ram:Name>
    <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">DE123456789</ram:ID></ram:SpecifiedTaxRegistration></ram:SellerTradeParty>
   <ram:BuyerTradeParty><ram:Name>Designstudio Test</ram:Name></ram:BuyerTradeParty>
  </ram:ApplicableHeaderTradeAgreement>
  <ram:ApplicableHeaderTradeSettlement>
   <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
   <ram:ApplicableTradeTax><ram:CalculatedAmount>19.00</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>
    <ram:BasisAmount>100.00</ram:BasisAmount><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>19</ram:RateApplicablePercent></ram:ApplicableTradeTax>
   <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    <ram:LineTotalAmount>100.00</ram:LineTotalAmount><ram:TaxBasisTotalAmount>100.00</ram:TaxBasisTotalAmount>
    <ram:TaxTotalAmount currencyID="EUR">19.00</ram:TaxTotalAmount><ram:GrandTotalAmount>119.00</ram:GrandTotalAmount>
    <ram:DuePayableAmount>119.00</ram:DuePayableAmount></ram:SpecifiedTradeSettlementHeaderMonetarySummation>
  </ram:ApplicableHeaderTradeSettlement>
 </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""

ADOBE_TEXT = """Adobe Systems Software Ireland Ltd
4-6 Riverwalk, Citywest Business Campus, Dublin 24, Ireland
VAT ID: IE6364992H

Rechnung
Rechnungsnummer: INV1234567890
Rechnungsdatum: 05.02.2025
Kunde: Designstudio Test, Musterstraße 1, 12345 Berlin

Creative Cloud All Apps – Monatsabo          59,49 EUR
Zwischensumme                                 59,49 EUR
USt 0 %                                        0,00 EUR
Gesamtbetrag                                  59,49 EUR

Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge, Art. 196 MwStSystRL).
"""

BUERO_TEXT = """Bürobedarf Meier GmbH
Hauptstraße 12, 80331 München
USt-IdNr. DE987654321

Rechnung Nr. 2025-1187                      Datum: 21.03.2025

Pos  Bezeichnung                 Menge   Einzelpreis   Gesamt
1    Kopierpapier A4 80g         5       4,99 €        24,95 €
2    Toner schwarz               1       58,90 €       58,90 €

Nettobetrag                                          83,85 €
zzgl. 19 % MwSt                                      15,93 €
Rechnungsbetrag                                      99,78 €

Zahlbar innerhalb von 14 Tagen.
"""


def text_pdf(text: str) -> bytes:
    pdf = MiniPdf(quer=False)
    for zeile in text.splitlines():
        pdf.zeile([(40, zeile, False)], groesse=10, hoehe=14)
    return pdf.bytes()


def zugferd_pdf() -> bytes:
    basis = text_pdf("Rechnung RE-2025-0042 – siehe eingebettetes XML")
    from pypdf import PdfReader
    w = PdfWriter()
    w.append(PdfReader(io.BytesIO(basis)))
    w.add_attachment("factur-x.xml", ZUGFERD_XML)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


CSV_SPARKASSE = """Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;Beguenstigter/Zahlungspflichtiger;Kontonummer/IBAN;BIC;Betrag;Waehrung;Info
DE00123;06.02.2025;06.02.2025;KARTENZAHLUNG;ADOBE SYSTEMS DUBLIN;Adobe Systems Software Ireland;IE00;XXX;-59,49;EUR;Umsatz gebucht
DE00123;24.03.2025;24.03.2025;ONLINE-UEBERWEISUNG;Rechnung 2025-1187;Buerobedarf Meier GmbH;DE99;XXX;-99,78;EUR;Umsatz gebucht
DE00123;28.03.2025;28.03.2025;GUTSCHRIFT;Logo Redesign RE 2025-03;Kunde Muster AG;DE77;XXX;1.500,00;EUR;Umsatz gebucht
DE00123;01.04.2025;01.04.2025;LASTSCHRIFT;Netflix Monatsabo;Netflix International;NL11;XXX;-17,99;EUR;Umsatz gebucht
"""

CAMT053 = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
 <BkToCstmrStmt><Stmt><Id>1</Id>
  <Ntry><Amt Ccy="EUR">59.49</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2025-02-06</Dt></BookgDt>
   <NtryDtls><TxDtls><RltdPties><Cdtr><Nm>Adobe Systems Software Ireland</Nm></Cdtr><CdtrAcct><Id><IBAN>IE00</IBAN></Id></CdtrAcct></RltdPties>
    <RmtInf><Ustrd>ADOBE SYSTEMS DUBLIN</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
  <Ntry><Amt Ccy="EUR">1500.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2025-03-28</Dt></BookgDt>
   <NtryDtls><TxDtls><RltdPties><Dbtr><Nm>Kunde Muster AG</Nm></Dbtr></RltdPties><RmtInf><Ustrd>Logo Redesign</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
 </Stmt></BkToCstmrStmt>
</Document>"""
