"""Stufe 1: ZUGFeRD / Factur-X / XRechnung. Eingebettetes XML aus dem PDF lesen
und strukturiert auswerten. Konfidenz 1.0, keine KI. Unterstützt CII (ZUGFeRD,
Factur-X, XRechnung-CII) und UBL (XRechnung-UBL).
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from datetime import date, datetime

XML_NAMEN = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml", "ZUGFeRD-invoice.xml", "cii.xml", "ubl.xml")


def eingebettete_xml(pdf_bytes: bytes) -> list[tuple[str, bytes]]:
    """Alle eingebetteten Dateien mit XML-Inhalt. Bekannte Namen zuerst."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    out: list[tuple[str, bytes]] = []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        anhaenge = reader.attachments  # name -> list[bytes]
        for name, inhalte in anhaenge.items():
            for inhalt in inhalte:
                if name.lower().endswith(".xml") or inhalt.lstrip().startswith(b"<"):
                    out.append((name, inhalt))
    except Exception:
        return []
    out.sort(key=lambda p: 0 if p[0] in XML_NAMEN else 1)
    return out


def _lokal(tag: str) -> str:
    return tag.split("}")[-1]


def _kind(el: ET.Element | None, *pfad: str) -> ET.Element | None:
    """Kind entlang lokaler Tag-Namen suchen (namespace-unabhängig)."""
    for name in pfad:
        if el is None:
            return None
        el = next((c for c in el if _lokal(c.tag) == name), None)
    return el


def _text(el: ET.Element | None, *pfad: str) -> str:
    k = _kind(el, *pfad) if pfad else el
    return (k.text or "").strip() if k is not None and k.text else ""


def _float(s: str) -> float | None:
    try:
        return float(s.replace(",", ".")) if s else None
    except ValueError:
        return None


def _datum(s: str) -> date | None:
    s = s.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10] if fmt != "%Y%m%d" else s[:8], fmt).date()
        except ValueError:
            continue
    return None


def parse_cii(root: ET.Element) -> dict:
    doc = _kind(root, "ExchangedDocument")
    trans = _kind(root, "SupplyChainTradeTransaction")
    agreement = _kind(trans, "ApplicableHeaderTradeAgreement")
    settlement = _kind(trans, "ApplicableHeaderTradeSettlement")
    seller = _kind(agreement, "SellerTradeParty")
    summ = _kind(settlement, "SpecifiedTradeSettlementHeaderMonetarySummation")

    ust_idnr = ""
    if seller is not None:
        for reg in (c for c in seller if _lokal(c.tag) == "SpecifiedTaxRegistration"):
            idel = _kind(reg, "ID")
            if idel is not None and idel.get("schemeID", "VA") == "VA":
                ust_idnr = (idel.text or "").strip()
                break

    saetze, kategorien, ust_summe = [], [], 0.0
    if settlement is not None:
        for tax in (c for c in settlement if _lokal(c.tag) == "ApplicableTradeTax"):
            p = _float(_text(tax, "RateApplicablePercent"))
            if p is not None:
                saetze.append(p)
            kategorien.append(_text(tax, "CategoryCode"))
            ust_summe += _float(_text(tax, "CalculatedAmount")) or 0.0

    netto = _float(_text(summ, "TaxBasisTotalAmount"))
    ust = _float(_text(summ, "TaxTotalAmount"))
    brutto = _float(_text(summ, "GrandTotalAmount")) or _float(_text(summ, "DuePayableAmount"))
    if ust is None:
        ust = ust_summe
    return {
        "format": "cii",
        "rechnungsnummer": _text(doc, "ID"),
        "datum": _datum(_text(doc, "IssueDateTime", "DateTimeString")),
        "lieferant": _text(seller, "Name"),
        "ust_idnr": ust_idnr.replace(" ", ""),
        "kaeufer": _text(_kind(agreement, "BuyerTradeParty"), "Name"),
        "waehrung": _text(settlement, "InvoiceCurrencyCode"),
        "betrag_netto": netto,
        "ust_betrag": ust,
        "betrag_brutto": brutto,
        "ust_satz": max(saetze) if saetze else (0.0 if kategorien else None),
        "steuer_kategorien": kategorien,
        "reverse_charge_hinweis": "AE" in kategorien,
        "beschreibung": _text(doc, "Name") or "",
    }


def parse_ubl(root: ET.Element) -> dict:
    supplier = _kind(root, "AccountingSupplierParty", "Party")
    total = _kind(root, "LegalMonetaryTotal")
    saetze, kategorien, ust = [], [], 0.0
    for tt in (c for c in root if _lokal(c.tag) == "TaxTotal"):
        ust += _float(_text(tt, "TaxAmount")) or 0.0
        for sub in (c for c in tt if _lokal(c.tag) == "TaxSubtotal"):
            kat = _kind(sub, "TaxCategory")
            p = _float(_text(kat, "Percent"))
            if p is not None:
                saetze.append(p)
            kategorien.append(_text(kat, "ID"))
    name = _text(supplier, "PartyName", "Name") or _text(supplier, "PartyLegalEntity", "RegistrationName")
    return {
        "format": "ubl",
        "rechnungsnummer": _text(root, "ID"),
        "datum": _datum(_text(root, "IssueDate")),
        "lieferant": name,
        "ust_idnr": _text(supplier, "PartyTaxScheme", "CompanyID").replace(" ", ""),
        "kaeufer": _text(_kind(root, "AccountingCustomerParty", "Party"), "PartyName", "Name"),
        "waehrung": _text(root, "DocumentCurrencyCode"),
        "betrag_netto": _float(_text(total, "TaxExclusiveAmount")),
        "ust_betrag": ust,
        "betrag_brutto": _float(_text(total, "TaxInclusiveAmount")) or _float(_text(total, "PayableAmount")),
        "ust_satz": max(saetze) if saetze else (0.0 if kategorien else None),
        "steuer_kategorien": kategorien,
        "reverse_charge_hinweis": "AE" in kategorien,
        "beschreibung": "",
    }


def parse_xml(xml_bytes: bytes) -> dict | None:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    lokal = _lokal(root.tag)
    if lokal == "CrossIndustryInvoice":
        return parse_cii(root)
    if lokal in ("Invoice", "CreditNote"):
        return parse_ubl(root)
    return None


def lese_erechnung(pdf_bytes: bytes) -> dict | None:
    """Erstes verwertbares E-Rechnungs-XML im PDF, sonst None."""
    for name, inhalt in eingebettete_xml(pdf_bytes):
        felder = parse_xml(inhalt)
        if felder and (felder.get("betrag_brutto") is not None or felder.get("betrag_netto") is not None):
            felder["xml_datei"] = name
            return felder
    return None


def lese_erechnung_xml_datei(xml_bytes: bytes) -> dict | None:
    """Für direkt zugestellte XRechnung-XML ohne PDF."""
    felder = parse_xml(xml_bytes)
    if felder:
        felder["xml_datei"] = "(direkt)"
    return felder
