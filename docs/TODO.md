# K-114 – att göra

Konkreta öppna uppgifter: sådant som behöver köras om, provas, utredas eller beslutas. Idéer som
inte är beställda står i `docs/IDEER.md`. Uppdaterat 2026-11-18 (kväll). Ta bort det som blir gjort
och för in det i rätt dokument (CLAUDE.md, `docs/system/`, `kalibrering/README.md`).

## Köra om

Inget just nu.

## Prova för hand (riktig terminal, macOS)

- Periskopets förstoring (`+`/`-` i hålläge, titt i hög) och bryggans kikare (`+`/`-` i bryggvyn).
- Övningen, periskopet i realtid, ubåtsvyn, hyttvyn (färgerna), sjökortets blyertsmärken.
- Sonarvyn (`sonar`): läsbarheten, relativ bäring under girar, kontaktraderna i små fönster.
- Att ctrl+p inte längre gör något, och att ett klick i loggen lämnar fokus i orderraden.
- Sömnen med starpom: att `sov` håller över en ny kontakt och att telefonen ringer för frågor.

## Utreda

Från provspelet 2026-11-18 (huvudlösa botar med blandade order och ja-boten):

- **Plottets benförslag mot land.** `sundet-ut`, frö 1, ja-boten: plottet föreslår `kurs 240` rakt mot
  stranden 0,1 nm bort; båten tar i botten. Navigatören säger inget, eftersom kortet visar land redan
  där besticket står (-10 m), och då är alla kurser lika dåliga i `_land_watch`. En `vetoes` i
  navigatören för kursförslag mot kortets land vore naturlig men flyttar spelet (kör `kontroll.py`).
- **Båten står tyst mot stranden.** I låg fart mot en brant strand flyttas båten tillbaka varje sekund
  (nu också kursen, se `seabed.bottom_contact`). Den står still med fart på loggen, besticket glider
  (0,35 nm på 20 min) och kursen blir aldrig "påkommen". Bara en `bottom.touch` i början.
- **Arktis: ytläge i en öppning korsad i annan vinkel.** `arktis-kort`, frö 4: navigatören stoppar under
  öppning 2 och föreslår ytläge, men för- och akterskeppet står under tjock is (`ice.bump`). Öppningens
  längd mäts längs banan där den loggades, inte längs vår kurs nu.
- **Arktis: vaken stannar i kanten.** Samma frö: `nav.suggest.up` (öppet vatten) och fem sekunder senare
  `nav.suggest.resume` (tjock is) när båten krupit eller isen drivit förbi kanten.
- **Pingar "för första gången" igen.** När sonar tappat jagaren säger den `sonar.ping.first` ("Någon
  söker") fast pingarna hörts i tolv minuter (`konvoj-mot`, frö 2, 06:45).

## Beslut som väntar på kaptenen

Inget just nu.

## Små brister i bilden

Inget just nu.
