from datetime import date

from app.models import Anlagegut, Buchung
from app.steuerlogik import (afa_fuer_jahr, betraege_vervollstaendigen, bewerte, erkenne_finanzamt, erkenne_reverse_charge, eur_zeilen, ust_abgleich,
                             konfidenz_aus_feldern, quartalsuebersicht, ust_13b, ustva)


def b(**kw) -> Buchung:
    basis = dict(datum=date(2025, 3, 1), richtung="ausgabe", betrag_netto=100.0, ust_satz=19.0, ust_betrag=19.0,
                 betrag_brutto=119.0, status="bestaetigt")
    basis.update(kw)
    return Buchung(**basis)


def test_betraege_aus_brutto_und_satz():
    assert betraege_vervollstaendigen(None, 19.0, None, 119.0) == (100.0, 19.0, 19.0, 119.0)


def test_betraege_aus_netto_und_ust():
    n, s, u, br = betraege_vervollstaendigen(83.85, None, 15.93, None)
    assert (n, u, br) == (83.85, 15.93, 99.78) and s == 19.0


def test_betraege_nur_brutto_bleibt_brutto():
    assert betraege_vervollstaendigen(None, None, None, 50.0) == (50.0, 0.0, 0.0, 50.0)


def test_kleinunternehmer_brutto_ist_betriebsausgabe(cfg, kats):
    bw = bewerte(b(), kats["software"], cfg)
    assert bw.abzugsfaehig == 119.0 and bw.eur_zeile == 50


def test_reverse_charge_erkennung(cfg):
    ok, gruende = erkenne_reverse_charge("Reverse Charge gemäß Art. 196", "IE6364992H", "Adobe Systems", 0.0, cfg)
    assert ok and len(gruende) == 3
    nicht, gruende = erkenne_reverse_charge("", "DE123456789", "Bürobedarf Meier", 19.0, cfg)
    assert not nicht
    # ausgewiesene USt widerspricht §13b
    nicht, gruende = erkenne_reverse_charge("", "IE6364992H", "Adobe", 11.3, cfg)
    assert not nicht and any("ausgewiesen" in g for g in gruende)


def test_reverse_charge_steuer_und_ustva(cfg, kats):
    rc = b(betrag_netto=59.49, ust_satz=0, ust_betrag=0, betrag_brutto=59.49, reverse_charge=True, ust_idnr="IE6364992H")
    assert ust_13b(rc, cfg) == 11.3
    u = ustva([rc], 2025, 1, cfg)
    assert u["kennzahlen"] == {"46": 59.49, "47": 11.3} and u["zahllast"] == 11.3
    us = b(betrag_netto=100, ust_satz=0, ust_betrag=0, betrag_brutto=100, reverse_charge=True, ust_idnr="US123456789")
    assert set(ustva([us], 2025, 1, cfg)["kennzahlen"]) == {"84", "85"}
    assert ustva([rc], 2025, 2, cfg)["positionen"] == []


def test_bewirtung_70_prozent_und_pflichtangaben(cfg, kats):
    bw = bewerte(b(betrag_brutto=100.0, betrag_netto=84.03, ust_betrag=15.97), kats["bewirtung"], cfg)
    assert bw.abzugsfaehig == 70.0 and bw.eur_zeile == 52
    assert any("Pflichtangaben" in w for w in bw.warnungen)
    bw2 = bewerte(b(meta_json='{"anlass": "Projektbesprechung", "teilnehmer": "A, B"}'), kats["bewirtung"], cfg)
    assert not bw2.warnungen


def test_gwg_grenze_erzeugt_afa(cfg, kats):
    klein = bewerte(b(betrag_netto=799.0, betrag_brutto=950.81, ust_betrag=151.81), kats["gwg"], cfg)
    assert klein.abzugsfaehig == 950.81 and klein.umwandeln_in is None
    gross = bewerte(b(betrag_netto=801.0, betrag_brutto=953.19, ust_betrag=152.19), kats["gwg"], cfg)
    assert gross.umwandeln_in == "anlagevermoegen" and gross.abzugsfaehig == 0.0
    assert gross.afa_vorschlag == {"nutzungsdauer_jahre": 3, "anschaffungskosten": 953.19}


def test_fahrtkosten_km_pauschale(cfg, kats):
    bw = bewerte(b(betrag_brutto=0, betrag_netto=0, ust_betrag=0, meta_json='{"km": 120}'), kats["fahrtkosten"], cfg)
    assert bw.abzugsfaehig == 36.0
    assert bewerte(b(), kats["fahrtkosten"], cfg).warnungen


def test_homeoffice_deckel(cfg, kats):
    bw = bewerte(b(betrag_brutto=0, betrag_netto=0, ust_betrag=0, meta_json='{"tage": 100}'), kats["arbeitszimmer"], cfg)
    assert bw.abzugsfaehig == 600.0
    # 200 Tage bisher = 1200 €, weitere 50 Tage würden 300 € geben, Deckel 1260 → nur 60 €
    bw2 = bewerte(b(betrag_brutto=0, betrag_netto=0, ust_betrag=0, meta_json='{"tage": 50}'), kats["arbeitszimmer"], cfg,
                  {"homeoffice_tage_bisher": 200})
    assert bw2.abzugsfaehig == 60.0 and bw2.warnungen


def test_privatanteil(cfg, kats):
    assert bewerte(b(betrag_brutto=60.0), kats["telekommunikation"], cfg).abzugsfaehig == 30.0
    assert bewerte(b(betrag_brutto=60.0, meta_json='{"privatanteil_prozent": 25}'), kats["telekommunikation"], cfg).abzugsfaehig == 45.0


def test_geschenke_grenze_je_empfaenger(cfg, kats):
    ok = bewerte(b(betrag_brutto=30.0, meta_json='{"empfaenger": "Kunde A"}'), kats["geschenke"], cfg, {"geschenke_je_empfaenger": {"Kunde A": 15.0}})
    assert ok.abzugsfaehig == 30.0
    zu_viel = bewerte(b(betrag_brutto=30.0, meta_json='{"empfaenger": "Kunde A"}'), kats["geschenke"], cfg, {"geschenke_je_empfaenger": {"Kunde A": 25.0}})
    assert zu_viel.abzugsfaehig == 0.0 and zu_viel.eur_zeile is None


def test_einnahme_mit_ust_warnt(cfg, kats):
    bw = bewerte(b(richtung="einnahme"), kats["einnahmen"], cfg)
    assert bw.eur_zeile == 11 and bw.warnungen


def test_afa_monatsgenau():
    a = Anlagegut(bezeichnung="MacBook", anschaffung=date(2025, 10, 1), anschaffungskosten=3600.0, nutzungsdauer_jahre=3)
    assert afa_fuer_jahr(a, 2025) == 300.0       # 3 Monate von 1200
    assert afa_fuer_jahr(a, 2026) == 1200.0
    assert afa_fuer_jahr(a, 2027) == 1200.0
    assert afa_fuer_jahr(a, 2028) == 900.0       # Rest
    assert afa_fuer_jahr(a, 2029) == 0.0
    assert afa_fuer_jahr(a, 2024) == 0.0


def test_quartalsuebersicht_und_eur(cfg, kats):
    kd = {k.id: k for k in kats.values()}
    buchungen = [
        b(kategorie_id=kats["software"].id, datum=date(2025, 1, 10), betrag_netto=59.49, ust_satz=0, ust_betrag=0, betrag_brutto=59.49, reverse_charge=True, ust_idnr="IE1"),
        b(kategorie_id=kats["buerobedarf"].id, datum=date(2025, 5, 2), betrag_netto=83.85, ust_betrag=15.93, betrag_brutto=99.78),
        b(kategorie_id=kats["bewirtung"].id, datum=date(2025, 8, 2), betrag_netto=84.03, ust_betrag=15.97, betrag_brutto=100.0),
        b(kategorie_id=kats["einnahmen"].id, datum=date(2025, 3, 28), richtung="einnahme", betrag_netto=1500, ust_satz=0, ust_betrag=0, betrag_brutto=1500),
        b(kategorie_id=kats["software"].id, datum=date(2025, 6, 1), status="vorschlag"),  # nicht bestätigt → ignoriert
        b(kategorie_id=kats["software"].id, datum=date(2024, 6, 1)),                      # anderes Jahr
    ]
    anlagen = [Anlagegut(bezeichnung="Monitor", anschaffung=date(2025, 1, 1), anschaffungskosten=1200.0, nutzungsdauer_jahre=3)]
    ue = quartalsuebersicht(buchungen, kd, anlagen, 2025, cfg)
    reihen = {r["kategorie"].schluessel: r for r in ue["zeilen"]}
    assert reihen["software"]["q"][0].brutto == 59.49 and reihen["software"]["q"][1].brutto == 0
    assert reihen["software"]["jahr"].ust == 11.3          # §13b-Steuer als entgangene Vorsteuer
    assert reihen["bewirtung"]["jahr"].abzugsfaehig == 70.0
    assert reihen["afa"]["jahr"].abzugsfaehig == 400.0
    assert ue["einnahmen"][4].brutto == 1500.0
    assert ue["entgangene_vorsteuer"][4] == round(11.3 + 15.93 + 15.97, 2)

    # Standard (Abflussprinzip): Zeile 48 nur aus Zahlungen ans Finanzamt – hier keine, also keine Zeile 48
    zeilen = {z["zeile"]: z["betrag"] for z in eur_zeilen(buchungen, kd, anlagen, 2025, cfg) if z["zeile"]}
    assert zeilen[11] == 1500.0 and zeilen[50] == 59.49 + 99.78 and zeilen[52] == 70.0 and zeilen[30] == 400.0 and 48 not in zeilen
    gewinn = next(z for z in eur_zeilen(buchungen, kd, anlagen, 2025, cfg) if z["bezeichnung"].startswith("Gewinn"))
    assert gewinn["betrag"] == round(1500 - 59.49 - 99.78 - 70 - 400, 2)
    # Alternative „rechnung“: §13b-Steuer je Rechnung bildet Zeile 48
    cfg_r = {**cfg, "ust_zeile48_basis": "rechnung"}
    zeilen = {z["zeile"]: z["betrag"] for z in eur_zeilen(buchungen, kd, anlagen, 2025, cfg_r) if z["zeile"]}
    assert zeilen[48] == 11.3
    gewinn = next(z for z in eur_zeilen(buchungen, kd, anlagen, 2025, cfg_r) if z["bezeichnung"].startswith("Gewinn"))
    assert gewinn["betrag"] == round(1500 - 59.49 - 99.78 - 70 - 400 - 11.3, 2)
    # Zahlung ans Finanzamt: zählt im Standard (Zeile 48), im Modus „rechnung“ nicht doppelt
    zahlung = b(kategorie_id=kats["ust_zahlung"].id, datum=date(2025, 4, 10), betrag_netto=11.3, ust_satz=0, ust_betrag=0, betrag_brutto=11.3)
    mit = buchungen + [zahlung]
    assert {z["zeile"]: z["betrag"] for z in eur_zeilen(mit, kd, anlagen, 2025, cfg) if z["zeile"]}[48] == 11.3
    assert {z["zeile"]: z["betrag"] for z in eur_zeilen(mit, kd, anlagen, 2025, cfg_r) if z["zeile"]}[48] == 11.3
    ab = ust_abgleich(mit, kd, 2025, cfg)
    assert ab["entstanden"] == 11.3 and ab["gezahlt"] == 11.3 and ab["offen"] == 0.0 and ab["zeile48"] == 11.3


def test_finanzamt_erkennung(cfg):
    assert erkenne_finanzamt("Finanzamt Gießen", "STEUERNR 039/852 UMS.ST 3.VJ 241.432,56 EUR", "ausgabe", cfg)[0] == "ust_zahlung"
    assert erkenne_finanzamt("Finanzamt Gießen", "Umsatzsteuer Erstattung 2024", "einnahme", cfg)[0] == "ust_erstattung"
    assert erkenne_finanzamt("Finanzamt Gießen", "EINKOMMENSTEUER VZ 2025 Q1 SOLI", "ausgabe", cfg)[0] == "einkommensteuer"
    assert erkenne_finanzamt("Landeshauptkasse", "EST 2024 Erstattung", "einnahme", cfg)[0] == "steuererstattung_privat"
    assert erkenne_finanzamt("REWE", "Einkauf Umsatzsteuer", "ausgabe", cfg)[0] is None
    k, grund = erkenne_finanzamt("Finanzamt Gießen", "Saeumniszuschlag", "ausgabe", cfg)
    assert k is None and "Steuerart" in grund


def test_konfidenz_aus_feldern():
    assert konfidenz_aus_feldern({}) == 0.0
    voll = {"datum": date.today(), "betrag_brutto": 1.0, "lieferant": "x", "rechnungsnummer": "1", "ust_satz": 19.0, "ust_idnr": "DE1"}
    assert konfidenz_aus_feldern(voll) == 1.0
    assert konfidenz_aus_feldern({"datum": date.today(), "betrag_brutto": 1.0}) == 0.55


def test_regeln_zusammenfuehren():
    from app.config import _zusammenfuehren
    standard = {"a": 1, "neu": 2, "kategorien": [{"schluessel": "fahrtkosten", "eur_zeile": 62, "beispiele": "km"}, {"schluessel": "zinsen", "eur_zeile": 56}], "eur_zeilen": {"1": "x", "2": "y"}}
    nutzer = {"a": 5, "kategorien": [{"schluessel": "fahrtkosten", "eur_zeile": 59}, {"schluessel": "eigene", "eur_zeile": 50}], "eur_zeilen": {"1": "mein x"}}
    m = _zusammenfuehren(standard, nutzer)
    assert m["a"] == 5 and m["neu"] == 2 and m["eur_zeilen"] == {"1": "mein x", "2": "y"}
    kats = {k["schluessel"]: k for k in m["kategorien"]}
    assert kats["fahrtkosten"]["eur_zeile"] == 62 and kats["fahrtkosten"]["beispiele"] == "km"   # alter Standard 59 → neuer Standard
    assert "zinsen" in kats and kats["eigene"]["eur_zeile"] == 50                                  # neu ergänzt, eigene bleibt
    nutzer2 = {"kategorien": [{"schluessel": "fahrtkosten", "eur_zeile": 40}]}
    assert {k["schluessel"]: k for k in _zusammenfuehren(standard, nutzer2)["kategorien"]}["fahrtkosten"]["eur_zeile"] == 40  # bewusst geändert bleibt


def test_kapitalanlage_erkennung(cfg):
    from app.steuerlogik import erkenne_kapitalanlage
    assert erkenne_kapitalanlage("Trade Republic Bank GmbH", "Kauf WKN A0RPWH ISIN IE00B4L5Y983", cfg)
    assert erkenne_kapitalanlage("ING", "Dividende Allianz SE", cfg)
    assert not erkenne_kapitalanlage("Adobe Systems", "Creative Cloud Abo", cfg)


def test_betriebsausstattung_wie_gwg(cfg, kats):
    """Betriebsausstattung: bis 800 € netto Sofortabzug (Zeile 33), darüber Anlagevermögen mit AfA."""
    klein = b(kategorie_id=kats["betriebsausstattung"].id, betrag_netto=249.0, ust_betrag=47.31, betrag_brutto=296.31)
    bw = bewerte(klein, kats["betriebsausstattung"], cfg)
    assert bw.eur_zeile == 33 and bw.abzugsfaehig == 296.31 and bw.umwandeln_in is None
    gross = b(kategorie_id=kats["betriebsausstattung"].id, betrag_netto=1500.0, ust_betrag=285.0, betrag_brutto=1785.0)
    bw = bewerte(gross, kats["betriebsausstattung"], cfg)
    assert bw.umwandeln_in == "anlagevermoegen" and bw.abzugsfaehig == 0.0 and bw.afa_vorschlag
