"""Stufe 2: Textebene digitaler PDFs über pdfplumber."""
from __future__ import annotations

import io


def pdf_text(pdf_bytes: bytes, max_seiten: int = 6) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            teile = []
            for seite in pdf.pages[:max_seiten]:
                teile.append(seite.extract_text() or "")
            return "\n".join(teile)
    except Exception:
        return ""


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
