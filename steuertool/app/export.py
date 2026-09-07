"""Ausgaben: EÜR-Liste, UStVA, Quartalstabelle (CSV + PDF), Belegjournal.
Der PDF-Schreiber ist absichtlich minimal und ohne Abhängigkeit: Helvetica,
WinAnsi (deckt Umlaute und € ab), Tabellenzeilen als Text.
"""
from __future__ import annotations

import csv
import io
import zlib
from datetime import date

from .models import Beleg, Buchung, Kategorie
from .steuerlogik import Zelle


def eur_fmt(x: float) -> str:
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " €"


# ------------------------------------------------------------------ CSV

def quartale_csv(ue: dict, modus: str = "brutto") -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Kategorie", "EÜR-Zeile", "Q1", "Q2", "Q3", "Q4", f"Jahr {ue['jahr']}", "Ansicht"])
    for r in ue["zeilen"]:
        k: Kategorie = r["kategorie"]
        w.writerow([k.name, k.eur_zeile or ""] + [_wert(z, modus) for z in r["q"]] + [_wert(r["jahr"], modus), modus])
    w.writerow([])
    w.writerow(["Summe Einnahmen", ""] + [_wert(z, modus) for z in ue["einnahmen"]])
    w.writerow(["Summe Ausgaben", ""] + [_wert(z, modus) for z in ue["ausgaben"]])
    w.writerow(["Gewinn (abzugsfähig)", ""] + [_num(g) for g in ue["gewinn"]])
    w.writerow(["Entgangene Vorsteuer (§19)", ""] + [_num(v) for v in ue["entgangene_vorsteuer"]])
    return buf.getvalue()


def _num(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _wert(z: Zelle, modus: str) -> str:
    return _num({"brutto": z.brutto, "netto": z.netto, "ust": z.ust, "abzugsfaehig": z.abzugsfaehig}[modus])


def eur_csv(zeilen: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Zeile", "Bezeichnung", "Betrag"])
    for z in zeilen:
        w.writerow([z["zeile"] or "", z["bezeichnung"], _num(z["betrag"])])
    return buf.getvalue()


def belegjournal_csv(buchungen: list[Buchung], belege: dict[int, Beleg], kategorien: dict[int, Kategorie]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Nr", "Datum", "Richtung", "Lieferant", "Beschreibung", "Rechnungsnr", "Netto", "USt-Satz", "USt", "Brutto",
                "Kategorie", "EÜR-Zeile", "§13b", "Status", "Konfidenz", "Extraktion", "Klassifizierung", "Belegdatei"])
    for i, b in enumerate(sorted(buchungen, key=lambda x: (x.datum, x.id or 0)), 1):
        k = kategorien.get(b.kategorie_id or -1)
        beleg = belege.get(b.beleg_id or -1)
        w.writerow([i, b.datum.strftime("%d.%m.%Y"), b.richtung, b.lieferant, b.beschreibung, b.rechnungsnummer,
                    _num(b.betrag_netto), _num(b.ust_satz), _num(b.ust_betrag), _num(b.betrag_brutto),
                    k.name if k else "", (k.eur_zeile if k else "") or "", "ja" if b.reverse_charge else "",
                    b.status, _num(b.konfidenz), b.extraktion_stufe, b.klassifizierung_weg,
                    beleg.dateipfad if beleg else ""])
    return buf.getvalue()


# ------------------------------------------------------------------ PDF

class MiniPdf:
    """Genug PDF für eine druckbare Tabelle: A4 quer, Helvetica, mehrere Seiten."""

    def __init__(self, quer: bool = True):
        self.b, self.h = (841.89, 595.28) if quer else (595.28, 841.89)
        self.seiten: list[list[str]] = []
        self.y = 0.0
        self.neue_seite()

    def neue_seite(self) -> None:
        self.seiten.append([])
        self.y = self.h - 50

    def _esc(self, s: str) -> str:
        return s.encode("cp1252", errors="replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def text(self, x: float, s: str, groesse: float = 9, fett: bool = False, rechts_bis: float | None = None) -> None:
        font = "/F2" if fett else "/F1"
        if rechts_bis is not None:
            breite = len(s) * groesse * 0.5
            x = rechts_bis - breite
        self.seiten[-1].append(f"BT {font} {groesse} Tf {x:.1f} {self.y:.1f} Td ({self._esc(s)}) Tj ET")

    def zeile(self, spalten: list[tuple[float, str, bool]], groesse: float = 9, fett: bool = False, hoehe: float = 14) -> None:
        if self.y < 50:
            self.neue_seite()
        for x, s, rechts in spalten:
            if rechts:
                self.text(0, s, groesse, fett, rechts_bis=x)
            else:
                self.text(x, s, groesse, fett)
        self.y -= hoehe

    def linie(self) -> None:
        self.seiten[-1].append(f"0.5 w 40 {self.y + 10:.1f} m {self.b - 40:.1f} {self.y + 10:.1f} l S")

    def bytes(self) -> bytes:
        objs: list[bytes] = []

        def add(o: bytes) -> int:
            objs.append(o)
            return len(objs)

        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        pages_nr = len(objs) + 1 + 2 * len(self.seiten)
        seiten_nr = []
        for inhalt in self.seiten:
            strom = zlib.compress("\n".join(inhalt).encode("latin-1"))
            c = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(strom) + strom + b"\nendstream")
            p = add((f"<< /Type /Page /Parent {pages_nr} 0 R /MediaBox [0 0 {self.b:.2f} {self.h:.2f}] "
                     f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {c} 0 R >>").encode())
            seiten_nr.append(p)
        kids = " ".join(f"{n} 0 R" for n in seiten_nr)
        pages = add(f"<< /Type /Pages /Kids [{kids}] /Count {len(seiten_nr)} >>".encode())
        assert pages == pages_nr
        root = add(f"<< /Type /Catalog /Pages {pages} 0 R >>".encode())

        out = io.BytesIO()
        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, o in enumerate(objs, 1):
            offsets.append(out.tell())
            out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
        xref = out.tell()
        out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
        for off in offsets:
            out.write(f"{off:010d} 00000 n \n".encode())
        out.write(f"trailer\n<< /Size {len(objs) + 1} /Root {root} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        return out.getvalue()


def quartale_pdf(ue: dict, modus: str = "brutto", stand: date | None = None) -> bytes:
    pdf = MiniPdf(quer=True)
    titel = {"brutto": "Brutto (= Betriebsausgabe bei §19)", "netto": "Netto", "ust": "Umsatzsteuer / entgangene Vorsteuer",
             "abzugsfaehig": "Abzugsfähig (nach Sonderregeln)"}[modus]
    pdf.zeile([(40, f"Quartalsübersicht {ue['jahr']} – {titel}", False)], groesse=14, fett=True, hoehe=22)
    pdf.zeile([(40, f"Stand {(stand or date.today()):%d.%m.%Y} · Kleinunternehmer §19 UStG · Anlage EÜR", False)], groesse=8, hoehe=18)
    sp = [40, 330, 420, 510, 600, 690, 800]
    pdf.zeile([(sp[0], "Kategorie", False), (sp[1], "Zeile", True), (sp[2], "Q1", True), (sp[3], "Q2", True),
               (sp[4], "Q3", True), (sp[5], "Q4", True), (sp[6], "Jahr", True)], fett=True)
    pdf.linie()
    for r in ue["zeilen"]:
        k = r["kategorie"]
        pdf.zeile([(sp[0], k.name[:48], False), (sp[1], str(k.eur_zeile or "–"), True)] +
                  [(sp[2 + i], eur_fmt(_f(r["q"][i], modus)), True) for i in range(4)] +
                  [(sp[6], eur_fmt(_f(r["jahr"], modus)), True)])
    pdf.linie()
    for name, zellen in (("Summe Einnahmen", ue["einnahmen"]), ("Summe Ausgaben", ue["ausgaben"])):
        pdf.zeile([(sp[0], name, False), (sp[1], "", True)] + [(sp[2 + i], eur_fmt(_f(zellen[i], modus)), True) for i in range(5)], fett=True)
    pdf.zeile([(sp[0], "Gewinn (abzugsfähige Beträge)", False), (sp[1], "", True)] +
              [(sp[2 + i], eur_fmt(ue["gewinn"][i]), True) for i in range(5)], fett=True)
    pdf.zeile([(sp[0], "Entgangene Vorsteuer durch §19", False), (sp[1], "", True)] +
              [(sp[2 + i], eur_fmt(ue["entgangene_vorsteuer"][i]), True) for i in range(5)])
    return pdf.bytes()


def _f(z: Zelle, modus: str) -> float:
    return {"brutto": z.brutto, "netto": z.netto, "ust": z.ust, "abzugsfaehig": z.abzugsfaehig}[modus]


def eur_pdf(zeilen: list[dict], jahr: int) -> bytes:
    pdf = MiniPdf(quer=False)
    pdf.zeile([(40, f"Anlage EÜR {jahr} – abtippfertig", False)], groesse=14, fett=True, hoehe=22)
    pdf.zeile([(40, "Zeile", False), (120, "Bezeichnung", False), (540, "Betrag", True)], fett=True)
    pdf.linie()
    for z in zeilen:
        pdf.zeile([(40, str(z["zeile"] or ""), False), (120, z["bezeichnung"][:70], False), (540, eur_fmt(z["betrag"]), True)],
                  fett=z["zeile"] is None)
    return pdf.bytes()
