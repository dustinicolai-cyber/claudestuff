"""Stufe 2: Textebene digitaler PDFs über pdfplumber."""
from __future__ import annotations

import io
import re


def pdf_text(pdf_bytes: bytes, max_seiten: int = 6) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            seiten = pdf.pages[:max_seiten]
            text = "\n".join(seite.extract_text() or "" for seite in seiten)
            if not _verklebt(text):
                return text
            # Manche Bank-PDFs (z. B. ING) setzen die Wörter so eng, dass pdfplumber sie ohne Leerzeichen
            # zusammenklebt („BudoschuleLeoGoldmitgliedschaft79,00EUR“). Dann enger tolerieren, bis die
            # Wörter auseinanderfallen – für das ganze Dokument die Variante mit den wenigsten Fehlern.
            beste, wert = text, _lesbarkeit(text)
            for toleranz in (2.3, 1.5):
                try:
                    kandidat = "\n".join(seite.extract_text(x_tolerance=toleranz) or "" for seite in seiten)
                except Exception:
                    continue
                w = _lesbarkeit(kandidat)
                if w < wert:
                    beste, wert = kandidat, w
            return beste
    except Exception:
        return ""


def _verklebt(text: str) -> bool:
    woerter = [w for w in text.split() if any(ch.isalpha() for ch in w)]
    if len(woerter) < 20:
        return False
    lang = sum(1 for w in woerter if len(w) > 20)
    return lang / len(woerter) >= 0.08


def _lesbarkeit(text: str) -> int:
    """Je kleiner, desto besser: zusammengeklebte Wörter zählen doppelt, auseinandergerissene einfach."""
    woerter = [w for w in text.split() if any(ch.isalpha() for ch in w)]
    verklebt = sum(1 for w in woerter if len(w) > 20)
    zerrissen = len(re.findall(r"\b[A-Za-zÄÖÜäöü]{1,2} [a-zäöüß]{3,}\b", text))
    return 2 * verklebt + zerrissen


def pdf_seiten_als_png(pdf_bytes: bytes, max_seiten: int = 2, skala: float = 2.0) -> list[bytes]:
    """Für Stufe 3: gescannte PDFs seitenweise rastern (pypdfium2 kommt mit pdfplumber)."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []
    out: list[bytes] = []
    try:
        doc = pdfium.PdfDocument(pdf_bytes)
        for i in range(min(len(doc), max_seiten)):
            bild = doc[i].render(scale=skala).to_pil()
            buf = io.BytesIO()
            bild.save(buf, format="PNG")
            out.append(buf.getvalue())
    except Exception:
        return out
    return out


def hat_textebene(text: str) -> bool:
    """Weniger als ~40 Buchstaben heißt praktisch: Scan ohne OCR-Ebene."""
    buchstaben = sum(ch.isalpha() for ch in text)
    return buchstaben >= 40
