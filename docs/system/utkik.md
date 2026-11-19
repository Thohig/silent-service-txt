# Bryggan och periskopet

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

- **Bryggan** (`stations/bridge.py`, `BridgeWatch`, roll vakthavande): tornluckan är sanning
  (`OwnSystems.bridge`: shut → manning 20 s i ytläge → manned → clearing 20 s vid order att dyka → shut);
  `OwnShip.bridge_open` håller djupet (depth_rate 0). Utkiken är en sensor: varannan sekund medan bryggan
  är bemannad `BridgeSighted` med en `PeriscopePicture` (eye "brygga", 8 m, ingen sektor) ⇒
  `Knowledge.bridge` (None vid utrymning). Fartyg i kikaren (7×50, `BINOC_POWER`): syns om `detectable` (se
  Periskopbilden), avstånd σ 12 % + 0,03 nm (strecksskalan, sämre än stadimetern); land och händelser med ögat 15 % + 0,05. Bäring σ 1°, kurs `AOB_SIGMA`,
  fart σ 3 kn; felen dras om var 60:e s per föremål (bilden fladdrar inte), och då får plottet en
  observation (`source="brygga"`). Egen slumpström (`game.rng_for("bridge")`).
  Ropar ut nytt eller > 5 min ur sikte; flyg i sikte eller jagare < 3 nm ⇒ förslag `djup 60`.
  Sonar skriver inte över en bättre klassning (utkikens GOD) med sämre.
  Vyn (`ui/bridge.py`, `ui/bridge_render.py`, `brygga`): 120° synfält åt `view_rel` relativt fören (← → 15°,
  mellanslag förut; `+` kikaren: periskopets okular med 7° mot blicken, `-` ögat igen), himmel (moln/stjärnor), horisont, sjö med vågor fasta i världen som driver med tiden,
  fördäck förut och kölvatten akterut, räcket nederst (land, vågkammar, moln, reling och kölvatten i braille i
  `_Grid.dots`, som periskopet delar); föremål ritas med periskopets `_draw_object`
  (siluett, lanternor, flyg, is), längre bort än 8 nm bara ett tecken. Bäringsskala, 360°-remsa
  (`render_strip(window=...)`) och datarad om föremålet närmast blickens mitt (±12°). Utan bild säger
  vyn varför ur `StatusSnapshot.bridge` och djupet.
  Utkiken ser också land (`LandBearing` var 3:e grad, `seabed.shore_ranges`: strålar mot `seabed.depths` ≤ 0 ut till sikten,
  på natten halva; avståndet ×(1 + σ 15 %) per minut), händelser bland `world.transients` varje tick
  (`EVENT_KINDS`: `splash` i dagsljus, `column` = sjunkbomb, `hit` = torpedens explosion, natt bara
  blixt/eld inom 12 nm; synliga 6/10/60 s) och spår efter ångtorpeder (inte SET-53) inom 1,5 nm i
  dagsljus. Ropar ut land (en gång per 5 min), vattenpelare (övning eller skarpt) och träffar.
- **Periskopet** (`stations/periscope.py`, `PeriscopeWatch`, roll vakthavande) är en sensor i realtid:
  medan masten är uppe läser det varje sekund World inom okularet (±16° kring `train`) och publicerar
  `PeriscopeSighted(live=True)` varannan sekund; svep (`periskop`, runt från förut på 15 s) och titt
  (`periskop 047`/`S-3`, 8 s) slutar med en bild `live=False` (inte om vi kom under periskopdjup).
  Hålläge: `periskop upp` … `periskop ned`, `vrid periskop 047` (tar över ett svep); fälls med
  `off.periscope.lowered` vid djup, fart > 7, is eller skada (`officer.mast_refusal`). Bedömningsfelen
  (`periscope.Judges`, delad med bryggan) dras en gång per hissning och föremål, i hålläge om var 60:e s;
  då får plottet en observation (bäring och avstånd efter förstoringen, `AOB_SIGMA`, fart 2). Nytt i
  okularet ropas ut en gång per hissning. Egen slumpström (`game.rng_for("periscope")`). Övningsledaren räknar bara `live=False`.
  Två förstoringar (`periscope.Optic`, `LOW`/`HIGH`): låg 1,5×, ±16°, bäring σ 1°, avstånd 15 % + 0,05 nm, kurs
  σ × 1,5; hög 6×, ±4°, bäring σ 0,5°, avstånd 8 % + 0,03 nm (stadimetern). Svepet söker och mäter i låg;
  titten söker i låg (±16°) och mäter i hög; hålläget i den valda (`förstoring hög`/`låg`, `PeriscopePower`,
  `Order.INSTRUMENT`). `search`/`measure`/`shown_power`; vyn får `StatusSnapshot.periscope_power` och
  bilden `PeriscopePicture.power`. Utropet i hög säger "hög förstoring" och "enligt stadimetern".
  Kikaren (`optic` "kikare", ytläge med bemannad brygga): samma order men ingen mast, ingen fartgräns,
  bilden är bryggans (`Knowledge.bridge`) inom synfältet, inga egna utrop eller plottobservationer
  (`off.binoculars.*`); fälls när bryggan utryms. I ytläge gäller ingen fartgräns för masten.
  Periskopvyn med bemannad brygga och nere periskop visar bryggans levande bild ("KIKARE, bryggan");
  blickens sanna bäring delas med bryggvyn (`SubApp.look_bearing`). Utryms bryggan blir dess sista bild
  `Knowledge.periscope` om den är nyare. Samma fartyg utan ändring (kurs < 15°, fart ≤ 3 kn) inom 5 min
  efter förra utropet: `off.periscope.again`. Hålläge > 60 s med ett hot i plottet: vakthavande föreslår
  `periskop ned` (var 3:e min).
  Land (`_observe_land`): samma strålar som bryggan (`seabed.shore_ranges`, ut till sikten, på natten halva;
  landet är högre än horisonten, så ögonhöjden spelar ingen roll), mätta när masten hissas och var 30:e s,
  men bara i de riktningar okularet sett under hissningen. Avståndet ×(1 + σ) en gång per hissning, σ efter
  förstoringen (`measure.range_rel`). `off.periscope.land` (närmaste bäring och avstånd) när land syns efter
  10 min utan; landet töms vid varje ny hissning (`_new_raising`).
  Händelser (`_observe_events`, P1–P2 2026-11-19): plask, vattenpelare och träffar i okularet, samma regler
  som bryggan (`stations/lookout.visible_events`, delad): plask bara i dagsljus, explosioner på natten som
  blixt ut till 12 nm, och bara det som når över horisonten plus vågtopparna (`periscope.event_visible`,
  höjder `EVENT_HEIGHT_M`: plask 5 m, pelare 25 m, träff 60 m; vågor `WAVE_M` efter Beaufort). Ögat 1,5 m
  upp ser alltså ett plask på ~6 nm (färre i grov sjö) och en pelare på ~12 nm. Bäring och avstånd med
  förstoringen man mäter med; syns `EVENT_S` (6/10/60 s) i bilden och ritas i okularet (`_draw_event`,
  delad med bryggvyn). `off.periscope.column` (larm om skarpt, högst var 5:e min) och `off.periscope.hit`.
  Både bryggan och periskopet publicerar `EventSighted`; plottet skriver ett blyertsmärke där det syntes
  (✕ plask, ✱ pelare/träff, ○ övning).
- **Periskopbilden** (`sim/periscope.py`): `Knowledge.periscope` håller den senaste bilden.
  Upptäckt (`detectable`): ett fartyg under horisonten (masttoppen, `HEIGHTS`) syns aldrig; annars om dess
  skenbara höjd över horisonten × förstoringen är minst `DETECT_ARCMIN` (1,5′). Med sikten 10 nm (alla
  scenarier i dagsljus) syns stora fartyg i båda förstoringarna; låg tappar patrullbåten bortom ~7 nm och
  jagaren bortom ~12 nm (bara med längre sikt). Titten letar i hög ±4° och i låg ±16° (`_spots`). Synlig del (helt/överbyggnad/mastoppar) ur ögonhöjd (periskop 1,5 m, brygga 8 m)
  och `HEIGHTS`; kursbedömningens σ (`AOB_SIGMA`) följer synlig del, natt = bara lanternor (σ 25°).
  Vinkel på bogen `aob` + styrbord. Fartyg bär plottets beteckning, aldrig sanningens id.
  Vyn (`ui/periscope_render.py`, `ui/periscope.py`): 360°-remsa med fören i mitten, okular (32° i låg och 8° i
  hög förstoring, `POWER_FOV`; i hög stadimeterns strecksskala på siktlinjen och gradering varje grad; rubriken
  säger förstoringen; + och − byter i hålläge; kanten,
  vågkammarna och landet i braille, `draw_land` delas med bryggan);
  masten uppe (`StatusSnapshot.periscope`/`periscope_train`/`periscope_up_s`): okularet står mot
  periskopets bäring, ← → vrider 5° (`vrid periskop`, `Order.INSTRUMENT`: inte i loggboken), mellanslag
  förut, ↓ ned; nere: mot valt föremål (← →), ↑ `periskop upp`; natt bara lanternor, bild äldre än 60 s nedtonad.
  Siluetterna i braille (`ui/silhouettes.py`, SB1–SB3 2026-11-19): varje fartygstyp är en profil i meter
  (skrov med språng och lutande förstäv, överbyggnader, skorstenar, master med rår; höjderna = `HEIGHTS`, testat),
  projicerad efter vinkeln på bogen (längden × |sin|, bredden × |cos|, fören åt höger på styrbordssidan) och
  skuren vid bildens avstånd där horisonten och vågtopparna skymmer (`hidden_height_m` + `WAVE_M`; vattenlinjen
  rör sig med tiden i grov sjö). Skalan är verklig (prickar per grad × vinkelstorleken), men masten är minst
  8 prickar hög i låg förstoring och från bryggan och 20 i hög och kikaren (`MIN_MAST_DOTS(_HIGH)`): i verklig
  skala är en jagare på 2 nm 18 × 5 prickar i hög och 4 × 1 i låg, alltså nästan osynlig; nära fartyg är
  verkliga och växer med förstoringen. Bogvåg i skum efter bedömd fart (≥ 4 kn), rök ur ångarnas skorstenar
  i dagsljus. Horisontens streck viker undan för skrovet, siktet ligger kvar ovanpå (`put_dots`). Bara
  mastoppar: bara masterna ritas. Vattenpelaren (`column_dots`) stiger på 2 s, sprutar ut upptill och sjunker
  ihop till skum på 10 s, övningsladdning hälften så hög; i okularet och på bryggan.
  Där okularet inte varit under hissningen följer föremål med från bilden före i 10 min (`seen_t`,
  ritas nedtonade); i ett svep eller en titt räknas allt som setts som sett nu.
  Is: `ice.ice_view` (periskopet är en sensor) ger kant och vallar i 16 riktningar ut till 0,6 nm;
  kommer masten inte upp för isen publiceras `PeriscopeBlocked` och vyn säger det.
