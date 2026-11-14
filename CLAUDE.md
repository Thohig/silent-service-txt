# K-114 – arbetsregler för Claude

Textbaserad ubåtssimulator i realtid: sovjetisk atomubåt (Projekt 627A-liknande),
oktober 1962. Python 3.12, Textual, numpy, uv. Användaren kör macOS (Apple Silicon).
Översikt, order och system finns i README.md – läs den först.

## Språk
- Svara användaren på svenska.
- Allt spelaren ser är svenska: fraser, order, rapporter. Kod, identifierare och
  kommentarer får vara svenska eller engelska, men följ omgivande fil.
- Decimaltal i spelet med komma (`fmt.nm`, `fmt.kn`), kurser tresiffriga (`fmt_course`).

## Kommandon
```bash
uv run main.py [--seed N] [--scenario kuba] [--tyst]   # spela (utan --scenario: väljare)
uv run pytest -q              # alla tester (~3 s), ska alltid vara gröna
```

## Designprinciper (får inte brytas)
1. **Spelaren räknar aldrig själv.** Besättningen räknar och rapporterar.
2. **Varje bedömning har kvalitet** (`Quality`: dålig, osäker, god, säker) som
   härleds ur datan, t.ex. TMA-kovarians. Slumpa aldrig fram kvalitet.
3. **Sanning och kunskap hålls isär.** Bara sensorer (`sim/sonar.py`, och
   periskop/radar/aktiv sonar i stationerna) läser `World`. `Knowledge` byggs
   enbart från händelser på bussen och har ingen referens till världen.
   Rapporter får aldrig avslöja sanningens id:n (`DD1`, `T1` …).
4. **`sim/` importerar aldrig Textual.** Gränssnittet bor i `ui/`.
5. **Besättningen föreslår åtgärder** via `Station.suggest(..., order="…")`;
   kaptenen svarar `ja`/`nej`. **Vapenavfyring föreslås aldrig som ja-order.**
   Förslag om sådant kaptenen redan beordrat släpps (`Game.suggestion_redundant`,
   `Order.STANDING`). Vid tystnad (10 min) tar vakthavande initiativ ur
   stationernas `idle_proposals()`.
6. Fast tidssteg 1 s. All slump via seedade `random.Random` – inga globala `random.*`.

## Arkitektur i korthet
- **Sanningslager:** `world.py` (tick-ordning dokumenterad där), `ownship.py`, `ice.py`,
  `enemy.py`, `weapons.py`, `environment.py`, `acoustics.py`, `entities.py`.
  Transienter/emissioner som skapas under ett tick blir hörbara nästa tick.
- **Stationer** (`sim/stations/`): en per system, ärver `Station`. Har `COMMANDS`
  (`CommandSpec`), `on_order`, `update`, `say`, `suggest`. Nya system = ny station
  i `DEFAULT_STATIONS`; `Game` ska inte behöva ändras.
- **Rapporter** bär `type` + `data`, aldrig färdig text. Texten skapas av
  `phrases.render()` vid leverans, efter rapportfiltren. Varje station registrerar
  sina fraser med `phrases.register({...})` i sin egen modul.
- **Scenarier** registreras i `sim/scenario.py` (`register(ScenarioDef(...))`) och
  väljs i gränssnittets väljare eller med `--scenario`. Scenariot bär områdesnamn
  och sluttexter; `Game` ska inte känna till enskilda scenarier.
- **Civil trafik:** `traffic.py` (sanning). `World.spawners` skickar in nya fartyg,
  `MerchantAI` styr dem. Neutrala fartyg (`World.neutral_ships`) är inte fiender; sänks
  ett slutar spelet (`neutral_sunk`). Kunskap: `ContactTrack.civil`/`warship`; civila
  räknas inte som hot men plottas tyst för kortet.
- **Flyg:** `air.py` (sanning). `AirPatrol` (en spawner) skickar ett plan i taget;
  `AircraftAI` söker med radar, bojar och MAD och ger jagaren datum (`DestroyerAI._set_datum`).
  Plan och bojar är `Vessel` som inte är fartyg (`is_ship` falskt, tysta). Besättningen
  märker flyget via radarvarnaren, periskopet och transienterna `buoy`/`buoy_ping`.
- **Is:** `ice.py` är sanning (bara isekolodet i `navigation.py` och mastkontrollerna
  `masts_clear` läser den); `icemap.py` är kunskap, byggd av `IceSounded` med
  beräknad position. Öppningars kvalitet = lägesosäkerhet (växer 8 m/min) mot
  halva längden.
- **Havsbotten:** `seabed.py` är sanning (`Environment.bottom_at`; bara ekolodet läser den).
  Scenariot ger också `chart_seabed`, det gamla sjökortets bild (`Seabed.chart_copy`:
  formerna flyttade, ingen ojämnhet, ibland utan berg) som blir `Knowledge.bathymetry`.
  Navigatören ritar djupkurvor ur den och loggar kortets djup längs besticket.
  Botten dras sist i scenariot så att övriga slumpdragningar inte flyttas.
- **Sjökortet**: `Station.chart_items()` ger ritelement (`sim/chart.py`) ur
  kunskapen i beräknade koordinater; `Game.chart()` samlar, `ui/chart_render.py`
  rastrerar (en rad = två kolumner i höjd). Nytt system ritar sig självt.
- **Djupprofilen** (`profil`): `Station.profile_items()` ger element (`sim/profile.py`):
  fasta djup (`Level`), navigatörens djuplogg (var 10:e s), ekolodets bottenlodningar
  (bara efter `ekolod`), isekolodets lodningar och sonarrummets hörda ljud. `Game.profile()`
  samlar, `ui/profile_render.py` ritar sidovyn (tid vågrätt, botten i eget band under
  bruten axel) och djupmätaren bredvid loggen. Tab växlar logg → sjökort → profil → logg.
- **Tangenter:** `Tab` växlar vy, `Esc` tillbaka, `ctrl+t` ljud. Undvik F-tangenter
  (medietangenter på Mac) och ctrl-tangenter som orderraden (`Input`) redan använder.
- **Ljud** (`ui/audio.py`): `SoundBoard` lyssnar bara på bussen – `ReportDelivered` ger tal
  (`say`, takt per roll) och larm (`CUE_BY_TYPE`); `SoundHeard` (med sensorns `se`) ger
  hydrofonljud panorerade efter relativ bäring (`TRANSIENT_SOUND`); `OwnSoundMade` ger egna
  ljud (ping, avfyring, skenmål, nödblåsning). Syntetiserade wav. Av som standard i `SubApp`.
  Bakgrundsljud (`ui/ambience.py`): `ambient_targets(status, tracks)` ur `StatusSnapshot`
  (inkl. `sea_noise`, `fire`, `smoke`, `ventilating`) och hållna kontaktspår; `Ambience`
  mixar sömlösa slingor i en sounddevice-ström. Kontaktljudet följer klassificeringen.
- **Händelsebussen** (`events.py`) är synkron. `Knowledge` registreras före
  stationerna så att stationer alltid ser uppdaterad kunskap.
- **Utbyggnadskrokar:** rapportfilter (`ReportQueue.filters`, ändrar `data`) för
  trötthet/lojalitet/sabotage; `CrewMember.effective_skill()` för all
  prestationspåverkan; prenumeration på `ReportDelivered` för tal (`say`).

## Kalibrering (ändra medvetet, kör sedan provspel)
- Språngskikt 60 m, 7 dB (`Thermocline` i `environment.py`). Arktis (`ArcticProfile`):
  inget skikt, sfäriskt till 1 nm sedan cylindriskt, isstudsar 2,4 dB/nm som halveras
  vid 150 m medeldjup. Kavitationsfart `6 + djup/25` kn.
- Jagare: källnivå `137 + 1,25·fart`; ping 230 dB; aktiv räckvidd ~4,4 nm över
  skiktet, ~2 nm under. Passivt hör den oss sällan om vi inte kaviterar.
- Egen ubåt: turbin 128 dB, smygmotor 112, reaktorpumpar 120 (går alltid när
  reaktorn är i drift). Vi hör jagaren på ~5–6 nm under skiktet i 5 kn.
- TMA: svaga antaganden (fart σ 30 kn, avstånd log-normal kring 6 nm), 30 min
  fönster, kvalitet ur σ_r/r (10/25/50 %), fart > 35 kn ⇒ dålig. Målmanöver vid
  chi² > 4 eller brytpunktstest > 15 (två raka ben före/efter 5 eller 10 min mot ett;
  raka mål ger median 2, max ~12). Plottlaget säger manöver högst var 5:e min per kontakt.
  Två ben i sicksack ska normalt ge god/säker lösning på ~20 min.
- Civil trafik (Kuba, `KUBA_TRAFFIC` i `scenario.py`): tre leder, 1,8 fartyg/h plus 3 från
  start, 9–14 kn, källnivå `140 + fart`. Maskering: neutralt fartyg inom 4° av målets
  bäring adderar sitt brus; ubåt < 100 m inom 0,3 nm från ett handelsfartyg får −12 dB eko
  hos jagaren. Jagaren hittar ja-boten i ~5 av 8 frön, som utan trafik.
- Ubåtsjaktflyg (Kuba, `KUBA_AIR`): första plan efter 40–80 min, 60–90 min över kvadraten,
  45–75 min mellan. Radar: master 6 nm (6 %/svep), ytläge 25 nm. MAD 250 m snedavstånd
  från 60 m höjd (säkert under ~190 m). Passiva bojar DT 8; aktiv boj 205 dB var 20:e s.
  Med flyg: jagaren hittar ja-boten i 9 av 12 frön (7 utan), flyget självt i 8 av 12.
- Botten (Kuba): djuphav 1 850–2 350 m, +15 m/nm norrut; bank 120–200 m med kanten 4,5–5,5 nm
  från väst- eller östsidan ⇒ ~15–18 % grundare än 300 m; berg med topp 250–400 m minst 4 nm
  från start; ränna 250–450 m djup. Kortets fel 0,5 nm (Arktis 0,8), berget saknas i 25 %.
  Arktis: slätt 3 300–3 800 m, rygg med krön 900–1 200 m ± 100–200 m.
- Provdjup 300 m, krossdjup 450 m, periskopdjup ≤ 18 m, antenndjup ≤ 30 m.
- Packis (`ice.py`): rutor 0,05 nm, flerårsis 2–4,5 m, kölar 8–25 m (6 % 30–45 m),
  170 råkar, 28 polynyor ⇒ ~4–5 % öppet vatten, en öppning ungefär var 30:e minut
  i 5 kn. Tornets topp 13 m och skrovets 8 m över kölen. Tunn is ≤ 1 m bryts i
  ≤ 2 kn på 40 s. Isdrift 0,25 kn mot 200°. Isbrus 50 dB (fast is) till 72 dB.
- Arktis: generatorn 142 dB, US-ubåt 125 + 1,5·fart med DT 0 och egenbrus 48 + fart.
  Mål: ytläge inom 1,5 nm från Nord-7. Ja-boten når målet i ~10 av 12 frön.
- Brand (arktis, 40–110 min): rök 0,0009/s medan det brinner (7–13 min), sedan
  +0,2/h tills ventilation (−0,02/min på periskopdjup, −0,05/min i ytläge). Rök 1,0 = förlorad.
  Röken sänker `effective_skill()` med upp till 50 %.

## Arbetssätt
- Bygg i steg och **committa efter varje steg** (användaren vill det). Vid större
  nya delar: föreslå struktur och invänta ok.
- Nytt system ⇒ tester i `tests/`. Statistiska påståenden (TMA, sonar) testas över
  flera seeds, inte ett enda lyckat frö.
- Verifiera spelkänslan med en huvudlös genomspelning: skapa `Game`, prenumerera
  på `ReportDelivered`, skriv ut rapporter, kör `g.tick()` i en loop (gärna med
  en bot som svarar `ja` på förslag). Skriv sådana skript i scratchpad, inte i repot.
- Gränssnittet kan provköras med `App.run_test()` och `save_screenshot()`.
- Sanningsloggen (`logs/truth-*.log`) visar exakta positioner, fiendens tillstånd
  och datum – använd den för felsökning.

## Fallgropar
- Döp aldrig en metod i en Textual-widget till `_render` (krockar med Textual).
- Timer-callbacks i `ui/app.py` kan köras under nedstängning – skydda mot `NoMatches`.
- Förslag spärras per nyckel med `cooldown`; glöm inte det, annars spammar
  besättningen.
- TMA antar rak kurs; om målet manövrerar ska plottlaget säga det och börja om
  (`ContactTrack.tma_from_t`), inte rapportera en orimlig lösning.
