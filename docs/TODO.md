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

Från provspelet 2026-11-18 (huvudlösa botar med blandade order och ja-boten). Utrett 2026-11-18 (kväll),
orsak och förslag till rättning; inget rättat än.

- **Plottets benförslag mot land.** `sundet-ut`, frö 1, ja-boten, 07:08: plottet föreslår `kurs 240`,
  båten tar i botten 07:11. *Orsak:* kortets strandlinje ligger ~0,15 nm öster om den sanna (kortets
  medvetna fel, `accuracy_nm` 0,3). Båten ligger i remsan mellan dem: sant 39 m, besticket bara 0,03 nm
  fel, men kortet visar land (-10 m). `chart_ahead` ger då -10 m på 0,0 nm för nästan alla kurser, så
  `_land_watch` tiger ("ingen kurs är bättre"), och plottets 240 (60° bort från kontakten) går mot den
  sanna stranden 0,06 nm bort. *Förslag:* (a) står besticket på kortets land: välj kursen med kortaste
  väg till kortets vatten och säg att kortet ligger fel här ("kortet visar land där vi står"); (b)
  `vetoes` i navigatören för kursförslag som enligt kortet går mot land närmare än nuvarande kurs, och
  plottet provar då giren åt andra hållet. Flyttar spelet (`kontroll.py`).
- **Båten står tyst mot stranden.** Samma körning, 07:14–07:32: båten står på samma punkt i 18 min,
  kurs 152 mot beordrad 150, fart 1 kn på loggen, `bottom_contact` hela tiden; besticket glider 0,35 nm.
  *Orsak:* giren 240 ⇒ 136 svängde in aktern (kölpunkt ~50 m bakom) i land. `bottom_contact` ställer
  tillbaka varje steg där någon kölpunkt är under botten, också steg som minskar intrånget, så båten
  kommer aldrig loss (framåt i 152 är bort från land). *Förslag:* godta steget om det inte gör det värre
  (grundaste kölpunkt inte grundare än före), och sätt farten genom vattnet till 0 medan båten står mot
  land så att loggen visar 0 och besticket inte glider; ny `bottom.touch` (eller "vi står mot land") om
  kontakten varar. Rör sanningslagret, kör `kontroll.py` och sundet-botarna.
- **Arktis: ytläge med förskeppet under is.** `arktis-kort`, frö 4, ja efter 5 s: öppning 1 loggad längs
  355, 171 m; vi ligger på samma kurs, så vinkeln var inte felet här. *Orsak:* båten glider förbi och
  stoppar med tornet i öppningens bortre ände, förskeppet under 2,8 m is redan när `nav.suggest.up` ges;
  navigatören prövar bara lodningen under tornet och öppningens längd, inte var tornet står i den. Under
  uppstigningen (barlast, ~4 min från 60 m) driver isen 0,25 kn, ~30 m, och aktern kommer också under is
  (två `ice.bump`). Med annan vinkel blir det värre: längden gäller bara längs banan. *Förslag:* föreslå
  ytläge bara om tornet står minst halva skrovet plus marginal (`sigma_m`) från öppningens båda ändar
  längs den loggade banan och kursen ligger inom ~20° från banans riktning; annars `vak` till mitten
  (`Opening.center`) i banans riktning först.
- **Arktis: vaken stannar i kanten.** Samma frö, ja efter 1 s: samma stopp i bortre änden (förskeppet
  under is), uppstigningen avbryts 02:41:52 (isen driver in, bra), sedan `nav.suggest.resume` (tjock is).
  *Orsak:* som ovan, plus att öppningens bredd tvärs banan är okänd och isen driver öppningen av tornet på
  ~2 min. *Förslag:* samma rättning som ovan (stoppa mitt i), och kanske påbörja uppstigningen till
  ~30 m redan under inflygningen så att tiden under öppningen blir kortare.
- **Pingar "för första gången" igen.** `konvoj-mot`, frö 2, ja-boten: sonar tappar S-4 06:45:18, pingen
  06:45:40 i bäring 112 (S-4:s) blir `sonar.ping.first`. *Orsak:* en ping utan beteckning matchas bara
  mot okända pingare (`okänd…`), inte mot kända som nyss pingat. *Förslag:* matcha också kända pingare
  inom bäringsgrinden som pingat senaste 15 min; de behåller sin nyckel (ingen "Någon söker"). Litet.

## Beslut som väntar på kaptenen

Inget just nu.

## Små brister i bilden

Inget just nu.
