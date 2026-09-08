"""Anonymisierte Texte echter Rechnungen (pdfplumber-Ausgabe) als Regressionstests."""

CONGSTAR = """congstar Kundenservice • Postfach 1165 • 61466 Kronberg Kundennummer 2210000000
Mandats-ID MA10000000
Rechnungsdatum 18.03.2025
Rechnungsnummer 7580000000
Seite 1 von 2
Fragen zu deiner Rechnung?
Max Muster
Musterweg 1
12345 Musterstadt Kontakt: www.congstar.de/kontakt
Service: 0221 79 700 700
Rechnung für Februar 2025
Hallo Zu zahlender Betrag: 20,00 €
Max Muster
Dein Vertrag:
Deine Rechnung vom
18.03.2025
congstar Allnet Flat M - 015100000000
für deine genutzten Leistungen vom Vertragsnr: 327000000
01.02.2025 - 28.02.2025
Leistungen congstar 20,00 €
wird fällig am
25.03.2025
Viele Grüße
Dein congstar Team
Der zu zahlende Betrag wird am 25.03.2025 von
folgendem Konto eingezogen:
IBAN: DE** 5001 **** 5411 38** **
Solltest nicht du diese Rechnung bezahlen, so leite bitte die
Rechnung an die entsprechende Person weiter. Gesamtbetrag: 20,00 €
Hilfe rund um deine Rechnung:
www.congstar.de/hilfe-service/rechnung
congstar - eine Marke der Postbank Saarbrücken Sitz der Gesellschaft: Bonn WEEE-Reg.-Nr: DE60800328
Telekom Deutschland GmbH IBAN: DE57 5901 0066 0166 4966 69 USt.-Id-Nr: DE122265872 Pflichtangaben:
Bayenwerft 12-14 HR: Amtsgericht Bonn HRB 5919 Gläubiger ID: DE93ZZZ00000078611 www.congstar.de/pflichtangaben
50678 Köln
Kundennummer 2210000000
Leistungen im Detail
Rechnungsdatum 18.03.2025
Rechnungsnummer 7580000000
Seite 2 von 2
Dein Vertrag:327000000
congstar Allnet Flat M - 015100000000
Leistung Brutto MwSt
(EUR) (%)
Monatsentgelte und Vergünstigungen auf Monatsentgelte
1 Grundpreis congstar Allnet Flat M (01.02.2025 - 28.02.2025) 20,00 € 19
20,00 €
Verbindungsentgelte für Rufnummer 015100000000
2 Verbindungen ins deutsche Festnetz 0,00 € 19
3 Verbindungen in deutsche Mobilfunknetze 0,00 € 19
0,00 €
Summe Vertrag 327000000 20,00 €
4 Steuerinformation Steuer % Netto Steuer Brutto
19 16,81 € 3,19 € 20,00 €
Info zu deinem Datenvolumen im Inland/EU für Februar 2025 Wichtige Hinweise zu deinen Vertragslaufzeiten
Verfügbar Verbraucht Vertragsnummer 327000000:
Datenvolumen mit hoher Geschwindigkeit 30 GB 2,77 GB Vertragsbeginn: 22.11.2022
Datenvolumen in gebuchten Datenpässen: 0 MB 0,00 MB Akt. Ende der Mindestvertragslaufzeit: keine Laufzeit
Datenvolumen mit reduzierter Geschwindigkeit: 0,00 MB Kündigungsfrist: jederzeit - mit einer Frist von einem Monat
Dein insgesamt verbrauchtes Datenvolumen: 2,77 GB
"""

AMAZON = """Rechnung
Zahlungsreferenznummer 4UW9D6X87F0NSAV6
Verkauft von Amazon EU S.à r.l., Niederlassung Deutschland
USt-IDNr. LU20260743
Rechnungsdatum
/Lieferdatum 29 Dezember 2025
MAX MUSTER
Rechnungsnummer LU571I5B0AEUI
MUSTERWEG 1
Zahlbetrag 144,49 €
MUSTERSTADT, 12345
DE
Umsatzsteuer erklärt durch Amazon EU S.a.r.L.
USt-IDNr. # LU20260743
Rechnungsadresse Lieferadresse Verkauft von
Max Muster Max Muster Amazon EU S.à r.l., Niederlassung Deutschland
Musterweg 1 Musterweg 1 Marcel-Breuer-Str. 12
Musterstadt, 12345 Musterstadt, 12345 80807 München
DE DE Deutschland
USt-IDNr. LU20260743
Bestellinformationen
Bestelldatum 26 Dezember 2025
Bestellnummer 302-0000000-0000000
Rechnungsdetails
Beschreibung Menge Stückpreis USt. % Stückpreis Zwischensumme
(ohne USt.) (inkl. USt.) (inkl. USt.)
Skullcandy Crusher ANC 2 Over-Ear Noise Cancelling Wireless-Kopfhörer 1 121,42 € 19% 144,49 € 144,49 €
mit Sensory Bass, Extra Charging Cable 50 Std. Akkulaufzeit, Skull-iQ,
ASIN: B0D3RP6TST
Versandkosten 0,00 € 0,00 € 0,00 €
Gesamtpreis 144,49 €
USt. % Zwischensumme USt.
(ohne USt.)
19% 121,42 € 23,07 €
USt. Gesamt 121,42 € 23,07 €
LU-BIO-04
Amazon EU S.à r.l. - 38 avenue John F. Kennedy, L-1855 Luxembourg
Sitz der Gesellschaft: L-1855 Luxemburg
Seite 1 von 1
"""
