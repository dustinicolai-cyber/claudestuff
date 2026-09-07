"""Mail-Import. Zwei Wege:
  A) IMAP, strikt readonly (select(readonly=True) + BODY.PEEK) – nichts wird als gelesen
     markiert, verschoben oder gelöscht. Passwort nur im Schlüsselbund (keyring).
  B) Apple Mail lokal: ~/Library/Mail/**/*.emlx ohne Netz parsen.

Beide liefern MailNachricht-Objekte; die Auswertung (Anhang → Pipeline,
Link → „manuell holen“) ist gemeinsam.
"""
from __future__ import annotations

import email
import email.policy
import imaplib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from sqlmodel import Session, select

from .. import config
from ..models import MailFund, MailZustand
from . import pipeline

KEYRING_DIENST = "steuertool-imap"
RE_LINK = re.compile(r"https?://[^\s\"'<>)\]]+", re.I)
LINK_KEYS = re.compile(r"rechnung|invoice|billing|receipt|beleg|download|\.pdf|account|konto|order|bestellung|payment|zahlung", re.I)


@dataclass
class MailNachricht:
    id: str
    absender: str
    absender_domain: str
    datum: datetime | None
    betreff: str
    anhaenge: list[tuple[str, bytes]] = field(default_factory=list)
    links: list[str] = field(default_factory=list)


# ------------------------------------------------------------ Einstellungen

def einstellungen_pfad() -> Path:
    return config.home_dir() / "mail.json"


def einstellungen() -> dict:
    p = einstellungen_pfad()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"imap": {"host": "", "user": "", "ordner": config.regeln()["mail"]["standard_ordner"], "aktiv": False},
            "emlx": {"pfad": str(Path.home() / "Library" / "Mail"), "ordner_filter": config.regeln()["mail"]["standard_ordner"], "aktiv": False}}


def einstellungen_speichern(e: dict) -> None:
    einstellungen_pfad().write_text(json.dumps(e, indent=2, ensure_ascii=False), encoding="utf-8")


def passwort_setzen(user: str, passwort: str) -> bool:
    try:
        import keyring
        keyring.set_password(KEYRING_DIENST, user, passwort)
        return True
    except Exception:
        return False


def passwort_lesen(user: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(KEYRING_DIENST, user)
    except Exception:
        return None


# ------------------------------------------------------------- Parsen

def _domain(adresse: str) -> str:
    return adresse.rsplit("@", 1)[-1].lower() if "@" in adresse else ""


def _links_aus_body(msg: EmailMessage) -> list[str]:
    links: list[str] = []
    for part in msg.walk():
        if part.get_content_maintype() != "text" or part.get_content_disposition() == "attachment":
            continue
        try:
            inhalt = part.get_content()
        except Exception:
            continue
        if not isinstance(inhalt, str):
            continue
        if part.get_content_subtype() == "html":
            for m in re.finditer(r"href=[\"']([^\"']+)[\"']", inhalt, re.I):
                links.append(m[1])
        links.extend(RE_LINK.findall(inhalt))
    # Dedup, relevante zuerst
    seen, out = set(), []
    for l in links:
        l = l.rstrip(".,;")
        if l.startswith("http") and l not in seen and not re.search(r"unsubscribe|abmelden|mailto:|privacy|datenschutz|impressum", l, re.I):
            seen.add(l)
            out.append(l)
    out.sort(key=lambda l: 0 if LINK_KEYS.search(l) else 1)
    return out[:5]


def nachricht_aus_bytes(roh: bytes, mid: str, extra_anhaenge: list[tuple[str, bytes]] | None = None) -> MailNachricht:
    msg = email.message_from_bytes(roh, policy=email.policy.default)
    name, adresse = parseaddr(str(msg.get("From", "")))
    try:
        datum = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
        if datum and datum.tzinfo:
            datum = datum.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        datum = None
    anhaenge: list[tuple[str, bytes]] = list(extra_anhaenge or [])
    for part in msg.iter_attachments():
        fn = part.get_filename() or ""
        ct = part.get_content_type()
        if fn.lower().endswith((".pdf", ".xml", ".png", ".jpg", ".jpeg")) or ct in ("application/pdf", "application/xml", "text/xml"):
            try:
                daten = part.get_payload(decode=True)
            except Exception:
                continue
            if daten:
                anhaenge.append((fn or f"anhang.{ct.split('/')[-1]}", daten))
    return MailNachricht(id=mid, absender=adresse or name, absender_domain=_domain(adresse), datum=datum,
                         betreff=str(msg.get("Subject", "")), anhaenge=anhaenge, links=_links_aus_body(msg))


# --------------------------------------------------------------- IMAP

def imap_scannen(host: str, user: str, passwort: str, ordner: str, ab_uid: int, limit: int = 200) -> tuple[list[MailNachricht], int]:
    """Nur Nachrichten mit UID > ab_uid. Gibt (Nachrichten, höchste gesehene UID)."""
    conn = imaplib.IMAP4_SSL(host)
    hoechste = ab_uid
    try:
        conn.login(user, passwort)
        typ, _ = conn.select(f'"{ordner}"', readonly=True)   # readonly: kein \Seen, kein Verschieben
        if typ != "OK":
            raise RuntimeError(f"Ordner „{ordner}“ nicht gefunden")
        typ, daten = conn.uid("SEARCH", None, f"UID {ab_uid + 1}:*")
        uids = [u for u in (daten[0].split() if daten and daten[0] else []) if int(u) > ab_uid]
        out: list[MailNachricht] = []
        for u in uids[-limit:]:
            typ, teile = conn.uid("FETCH", u, "(BODY.PEEK[])")  # PEEK: Flags bleiben unangetastet
            if typ != "OK" or not teile or not isinstance(teile[0], tuple):
                continue
            out.append(nachricht_aus_bytes(teile[0][1], f"imap:{host}:{ordner}:{u.decode()}"))
            hoechste = max(hoechste, int(u))
        return out, hoechste
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# --------------------------------------------------------------- emlx

def emlx_lesen(pfad: Path) -> bytes | None:
    """Apple-Mail-Format: erste Zeile = Länge, dann die Rohmail, dann ein plist."""
    try:
        with open(pfad, "rb") as f:
            erste = f.readline()
            n = int(erste.strip() or 0)
            return f.read(n) if n else f.read()
    except (OSError, ValueError):
        return None


def _emlx_anhaenge(pfad: Path) -> list[tuple[str, bytes]]:
    """Bei .partial.emlx liegen Anhänge separat unter ../Attachments/<id>/<teil>/."""
    mid = pfad.name.split(".")[0]
    att_dir = pfad.parent.parent / "Attachments" / mid
    out: list[tuple[str, bytes]] = []
    if att_dir.is_dir():
        for f in att_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in (".pdf", ".xml", ".png", ".jpg", ".jpeg"):
                out.append((f.name, f.read_bytes()))
    return out


def emlx_scannen(wurzel: Path, ordner_filter: str, bekannte_ids: set[str], limit: int = 500) -> list[MailNachricht]:
    """Alle .emlx unter der Wurzel, deren Mailbox-Pfad den Ordnerfilter enthält (z.B. „Belege“)."""
    out: list[MailNachricht] = []
    if not wurzel.is_dir():
        return out
    for pfad in wurzel.rglob("*.emlx"):
        if ordner_filter and ordner_filter.lower() not in str(pfad).lower():
            continue
        mid = f"emlx:{pfad}"
        if mid in bekannte_ids:
            continue
        roh = emlx_lesen(pfad)
        if not roh:
            continue
        extra = _emlx_anhaenge(pfad) if ".partial." in pfad.name else None
        out.append(nachricht_aus_bytes(roh, mid, extra))
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------ Auswertung

def ist_relevant(n: MailNachricht, cfg: dict) -> tuple[bool, bool]:
    """(bekannter Absender, Betreff passt)"""
    domains = cfg["mail"]["bekannte_domains"]
    bekannt = any(n.absender_domain == d or n.absender_domain.endswith("." + d) for d in domains)
    betreff = n.betreff.lower()
    heur = any(k in betreff for k in cfg["mail"]["betreff_heuristik"])
    return bekannt, heur


def nachrichten_verarbeiten(s: Session, nachrichten: list[MailNachricht], ki_erlaubt: bool = True) -> dict:
    """Anhang → Pipeline (bekannter Absender: direkt; sonst als Vorschlag markiert).
    Nur Link → Liste „manuell holen“. Rückgabe: Zähler."""
    cfg = config.regeln()
    z = {"importiert": 0, "duplikate": 0, "vorschlaege": 0, "links": 0, "ignoriert": 0}
    bekannte = {m.mail_id for m in s.exec(select(MailFund)).all()}
    for n in nachrichten:
        bekannt, heur = ist_relevant(n, cfg)
        if not bekannt and not heur:
            z["ignoriert"] += 1
            continue
        if n.anhaenge:
            for name, daten in n.anhaenge:
                erg = pipeline.importiere_datei(s, daten, name, herkunft=f"mail:{n.absender}", ki_erlaubt=ki_erlaubt)
                if erg.status == "duplikat":
                    z["duplikate"] += 1
                    continue
                z["importiert"] += 1
                if not bekannt and n.id not in bekannte:
                    # Unbekannter Absender: Import bleibt Vorschlag und wird zusätzlich gelistet
                    s.add(MailFund(absender=n.absender, datum=n.datum, betreff=n.betreff, link="", mail_id=n.id,
                                   art="vorschlag", beleg_id=erg.beleg_id))
                    z["vorschlaege"] += 1
            s.commit()
        elif n.links and n.id not in bekannte:
            s.add(MailFund(absender=n.absender, datum=n.datum, betreff=n.betreff, link=n.links[0], mail_id=n.id, art="link"))
            z["links"] += 1
            s.commit()
    return z


def zustand(s: Session, konto: str, ordner: str) -> MailZustand:
    z = s.exec(select(MailZustand).where(MailZustand.konto == konto, MailZustand.ordner == ordner)).first()
    if not z:
        z = MailZustand(konto=konto, ordner=ordner)
        s.add(z)
        s.commit()
        s.refresh(z)
    return z


def imap_lauf(s: Session, ki_erlaubt: bool = True) -> dict:
    e = einstellungen()["imap"]
    if not e.get("host") or not e.get("user"):
        return {"fehler": "IMAP nicht konfiguriert"}
    pw = passwort_lesen(e["user"])
    if not pw:
        return {"fehler": "Kein Passwort im Schlüsselbund – bitte unter Mail-Einstellungen hinterlegen"}
    konto = f"imap:{e['host']}/{e['user']}"
    zs = zustand(s, konto, e["ordner"])
    try:
        nachrichten, hoechste = imap_scannen(e["host"], e["user"], pw, e["ordner"], int(zs.letzte_uid or 0))
    except Exception as ex:
        return {"fehler": f"IMAP: {ex}"}
    erg = nachrichten_verarbeiten(s, nachrichten, ki_erlaubt)
    zs.letzte_uid = str(hoechste)
    zs.zuletzt_gescannt = datetime.now()
    s.add(zs)
    s.commit()
    erg["neue_mails"] = len(nachrichten)
    return erg


def emlx_lauf(s: Session, ki_erlaubt: bool = True) -> dict:
    e = einstellungen()["emlx"]
    wurzel = Path(e.get("pfad") or "").expanduser()
    if not wurzel.is_dir():
        return {"fehler": f"Ordner nicht gefunden: {wurzel}"}
    konto = f"emlx:{wurzel}"
    zs = zustand(s, konto, e.get("ordner_filter", ""))
    bekannte = {m.mail_id for m in s.exec(select(MailFund)).all()}
    try:
        gesehen = set(json.loads(zs.letzte_uid)) if zs.letzte_uid.startswith("[") else set()
    except json.JSONDecodeError:
        gesehen = set()
    nachrichten = emlx_scannen(wurzel, e.get("ordner_filter", ""), bekannte | gesehen)
    erg = nachrichten_verarbeiten(s, nachrichten, ki_erlaubt)
    gesehen |= {n.id for n in nachrichten}
    zs.letzte_uid = json.dumps(sorted(gesehen)[-5000:])
    zs.zuletzt_gescannt = datetime.now()
    s.add(zs)
    s.commit()
    erg["neue_mails"] = len(nachrichten)
    return erg
