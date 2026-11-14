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
- **Konvoj:** `convoy.py` (sanning). `Convoy` är en spawner med en ledpunkt som sicksackar efter
  `ZIGZAG_PLANS` (medelavdrift ~0) kring baskursen; `ConvoyShipAI` håller platsen (fast i baskursens
  riktning). Nödgir 50° bort från hotet, +3 kn i 15 min (sänkt fartyg, egen torped < 1,5 nm,
  detonation < 4 nm), sedan baskurs och plan igen. Typer `transport` (145 + fart dB) och `tanker` (143).
  Eskort (`EscortAI(DestroyerAI)`, `make_escorts`): skärm 2,5 nm framför och 1,5 nm åt sidorna, fast
  i baskursens riktning; ping var 20:e s; skarpa från start (`roe="lethal"`); koppel 4 nm från
  ledpunkten; en jagar i taget (`Convoy.hunter`), den andra bara om datumet ligger < 1,5 nm från
  konvojen. Konvojens brus skymmer ubåten (`masking_noise(sides=...)`). Ubåt 1 nm från konvojens väg,
  3 kn: hittas i 8 av 8 frön på 50 och 150 m, ~25 min efter start (2–4 nm), ett anfall, sedan går
  konvojen vidare och eskorten släpper.
- **Flyg:** `air.py` (sanning). `AirPatrol` (en spawner) skickar ett plan i taget;
  `AircraftAI` söker med radar, bojar och MAD och ger jagaren datum (`DestroyerAI._set_datum`).
  Plan och bojar är `Vessel` som inte är fartyg (`is_ship` falskt, tysta). Besättningen
  märker flyget via radarvarnaren, periskopet och transienterna `buoy`/`buoy_ping`.
- **Is:** `ice.py` är sanning (bara isekolodet i `navigation.py`, mastkontrollerna
  `masts_clear` och periskopets `ice_view` läser den); `icemap.py` är kunskap, byggd av `IceSounded` med
  beräknad position. Öppningars kvalitet = lägesosäkerhet (växer 8 m/min) mot
  halva längden.
- **Havsbotten:** `seabed.py` är sanning (`Environment.bottom_at`; bara ekolodet läser den).
  Scenariot ger också `chart_seabed`, det gamla sjökortets bild (`Seabed.chart_copy`:
  formerna flyttade, ingen ojämnhet, ibland utan berg) som blir `Knowledge.bathymetry`.
  Navigatören ritar djupkurvor ur den och loggar kortets djup längs besticket.
  Botten dras sist i scenariot så att övriga slumpdragningar inte flyttas.
  Bottenkontakt (`seabed.bottom_contact`, efter förflyttningen): ≤ 2 kn sätter sig kölen
  utan skador, annars grundstötning (skrov −0,015·fart, sonar/roder efter var, läcka > 5 kn);
  trimmen tar oss 15 m upp. Navigatören (`_shoal_watch`, var 20:e s) ser på kortet 6 min
  framåt (minst 1 nm) ± bestickets σ åt sidorna, och en färsk lodning; föreslår djup
  30 m över botten. `NavigationStation.depth_limit()` begränsar sonarens djupförslag.
  Ligga på botten (`botten`, `OwnSystems.settle`/`on_bottom`): saktar till 1 kn, går ned först
  under 1,5 kn, sätter sig vid kontakt; World flyttar oss inte. Ljud: maskin 100 + pumpar 112 dB
  (mot 112/128 + 120). Ekoavdrag (`bottom_clutter`): 25 dB stilla på botten, 10 dB inom 20 m.
  Jagare 3 nm bort med datum 1 nm fel: hittar oss i 10 av 12 (12 av 12 svävande), första
  kontakt efter ~11 min (~6), 45 % färre ekon. Bottentyp: klippa vid berg/rygg och brantare
  än 450 m/nm, sand grundare än 400 m, annars lera; klippa ger skrov −0,03.
  Fix mot botten (`bottenfix`, `seabed.match_soundings`): 9 lodningar var 20:e s i ≥ 2 kn;
  sannolikhet över förskjutningar (±3σ, steg 0,05 nm) med lodfel 8 % + 20 m och besticket
  som förhandsantagande. Avvisas om chi²/lodning > 4 (kortet saknar något) eller om σ inte
  smalnar under 0,8·bestickets σ (flat botten). Ny σ = √(σ_match² + kortets noggrannhet²),
  `fix_sigma` i stället för 0,1. Lägeslinje om minsta axeln < halva största. Föreslås bara
  om bestickets σ ≥ 2 × kortets noggrannhet, brant botten och ingen brand, rök eller läcka. Över banken
  med 0,8 nm fel: medel 0,75 nm efter (angivet ~0,93); över berget 0,53 nm.
- **Sjökortet**: `Station.chart_items()` ger ritelement (`sim/chart.py`) ur
  kunskapen i beräknade koordinater; `Game.chart()` samlar, `ui/chart_render.py`
  rastrerar (en rad = två kolumner i höjd). Nytt system ritar sig självt.
- **Djupprofilen** (`profil`): `Station.profile_items()` ger element (`sim/profile.py`):
  fasta djup (`Level`), navigatörens djuplogg (var 10:e s), ekolodets bottenlodningar
  (bara efter `ekolod`), isekolodets lodningar och sonarrummets hörda ljud. `Game.profile()`
  samlar, `ui/profile_render.py` ritar sidovyn (tid vågrätt, botten i eget band under
  bruten axel) och djupmätaren bredvid loggen. Tab växlar logg → sjökort → profil → systemtavla → periskopbild → logg (`VIEWS` i `ui/app.py`).
- **Systemtavlan** (`system`): `Station.system_items()` ger element (`sim/systems.py`):
  `Gauge` (panel, etikett, text, tillstånd ok/info/av/varning/fara, ev. stapel), `Compartment`
  (nio avdelningar, maskin), `TubeRack` (torpedrum), `Flooding`. Ur egna instrument
  (`own.sys`), aldrig om fienden. `Game.systems()` samlar, `ui/systems_render.py` ritar
  genomskärningen och panelerna (okända paneler hamnar sist, så nytt system ritar sig självt).
- **Periskopbilden** (`sim/periscope.py`): vakthavande publicerar `PeriscopeSighted` med en
  `PeriscopePicture` när svepet är klart (inte om vi kom under periskopdjup); `Knowledge.periscope`
  håller den senaste. Synlig del (helt/överbyggnad/mastoppar) ur ögonhöjd (periskop 1,5 m, brygga 8 m)
  och `HEIGHTS`; kursbedömningens σ (`AOB_SIGMA`) följer synlig del, natt = bara lanternor (σ 25°).
  Vinkel på bogen `aob` + styrbord. Fartyg bär plottets beteckning, aldrig sanningens id.
  Vyn (`ui/periscope_render.py`, `ui/periscope.py`): 360°-remsa med fören i mitten, okular (32°)
  mot valt föremål (← →), siluetter i `ART` (fören åt höger, speglas vid babord, trycks ihop efter
  |sin vpb|, skärs efter synlig del), natt bara lanternor, bild äldre än 60 s nedtonad.
  Kort titt (`periskop 047`, `periskop S-3`): 8 s mast uppe i stället för 15, ser bara ±16°;
  föremål utanför sektorn följer med från förra bilden i 10 min (`seen_t`, ritas nedtonade).
  Is: `ice.ice_view` (periskopet är en sensor) ger kant och vallar i 16 riktningar ut till 0,6 nm;
  kommer masten inte upp för isen publiceras `PeriscopeBlocked` och vyn säger det.
- **Tangenter:** `Tab` växlar vy, `Esc` tillbaka, `ctrl+t` ljud. Undvik F-tangenter
  (medietangenter på Mac) och ctrl-tangenter som orderraden (`Input`) redan använder.
- **Ljud** (`ui/audio.py`): `SoundBoard` lyssnar bara på bussen – `ReportDelivered` ger tal
  (`say`, takt per roll) och larm (`CUE_BY_TYPE`); `SoundHeard` (med sensorns `se`) ger
  hydrofonljud panorerade efter relativ bäring (`TRANSIENT_SOUND`); `OwnSoundMade` ger egna
  ljud (ping, avfyring, skenmål, nödblåsning). Syntetiserade wav. Av som standard i `SubApp`.
  Bakgrundsljud (`ui/ambience.py`): `ambient_targets(status, tracks)` ur `StatusSnapshot`
  (inkl. `sea_noise`, `fire`, `smoke`, `ventilating`) och hållna kontaktspår; `Ambience`
  mixar sömlösa slingor i en sounddevice-ström. Kontaktljudet följer klassificeringen.
- **Ryska** (`sim/russian.py`): fasta fraser i `WORDS` (translitterering, kyrilliska, svensk
  betydelse). Skriv dem med `ru("Jest")` i fraserna; betydelsen ska framgå av svensk text bredvid,
  aldrig siffror eller bedömningar på ryska. `segments()` delar texten; talet läser ryskan med
  `RU_VOICE` (Milena) och resten med Alva. Ordlistan visas i `hjälp`. Stridslarm (`off.battle_stations`,
  revun) när jakttecken kommer efter 30 min lugn; avdelningarna rapporterar (`eng.inspected`)
  60 s efter haverilarm eller kraftig tryckvåg.
- **Ryskt tal**: varje station registrerar `RU_PHRASES` med `phrases.register_ru()` ur samma `data`;
  `render()` fyller `Report.speech` (kyrilliskt), annars `russian.fallback()` (vem som rapporterar).
  Hjälp i `russian.py`: `course` (siffra för siffra), `count`/`dec` med rätt böjning, `contact`
  (S-1 → цель 1), `CLASS_RU`. Inget latinskt i talet (testas). `SoundBoard.language` ("ru" som
  standard, `tal ryska`/`tal svenska`); utan Milena svenskt tal. Ny fras ⇒ lägg till rysk fras.
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
- Jagare (alla scenarier): död zon under skrovet, ingen eko om horisontellt avstånd < djup/tan 20°
  (200 m ⇒ 0,3 nm), så en djup ubåt tappas i slutet av anfallet. Döv 60 s efter en detonation
  inom 1,5 nm. Jagare hör inte sina egna sidans pingar. Kuba efter detta: ja-boten hittas
  fortfarande 8 av 8, men jagaren tappar och återfinner kontakt 2–20 gånger (förut 1) och
  anfaller 1–19 gånger (förut 2–37).
- Sonar publicerar `HuntSigns` vid snabb pingtakt och plask; `Knowledge.hunted()` (5 min). Då
  föreslår maskin `eng.suggest.sprint` (turbin, djup ≤ 220 m, fart = kavitationsfart − 1)
  i stället för smygmotor, och sonar föreslår inte fart 4 när en kontakt tappas.
- Jagade (`jagad`, `hunted_scenario`): ubåten börjar 45 m, 6 kn, 1,3 nm från bankens
  300-meterskurva på djupt vatten; DD1 2,2–3 nm i norr med färsk kontakt (`start_hunt`), DD2
  7–8,5 nm i söder. Jagarna är `partners` och delar fix (σ + 0,4 nm). `escalate_after=3`:
  skarpa efter tre övningsanfall (~25 min). `leash_nm=1`: släpper jakten när datumet ligger mer
  än 1 nm utanför kvadraten. Mål `mission["escape"]`: 1 nm utanför och ingen jägare med datum
  inom max(1 nm, 3σ) från oss (ett skenmål räknas inte). Navigatören (`exit_route`) föreslår
  närmaste kant, +4 nm straff inom 40° från en hotkontakt. 8 frön: passiv 0, ja-boten 3,
  djupt och fort (turbin 12 kn, 200 m, rakt ut) 7.
- Kust (`seabed.Coast`, `strait_seabed`): land har negativt djup (`Seabed.min_depth` < 0),
  sjökortet ritar land (`░`) och kustlinje. Tidvatten (`environment.TidalStream`, period 12 h 25 min)
  skalar med djupet: `peak·clamp(60/djup, 0,2, 1,5)`; `Environment.current_at(x, y, t)` används för
  alla fartyg och torpeder. Navigatören räknar besticket med `Knowledge.tide_table` (fel ±20 % och
  ±20 min) och lägger 0,3·|tidvatten| per timme på σ. Landvarning (`_land_watch`) föreslår gir när
  kortet visar < 21 m framåt. Fix nära land (land inom 8 nm dag, 5 natt): 30 s / 45 s, σ 0,05.
  Vägen ut (`exit_route`) går aldrig över land; finns ingen rak väg söker den på kortets rutnät.
  Efterklang på grunt vatten (`seabed.shallow_reverb`): aktiv sonar −15 dB vid 0 m, 0 vid 100 m.
  Navigatören tittar 6 min framåt, minst 0,6 nm (förut 1 nm).
- Hamnskydd (`harbor.py`): hydrofoner DT 10, rundstrålande: kustbrus 64 dB plus alla fartyg inom
  5 nm (smygmotor 3 kn hörs < 0,15 nm, turbin 5 kn ~0,5 nm; ett fartyg nära dränker oss). Nät med
  grind ±0,1 nm som är öppen 4 min efter att ett fartyg varit inom 1 nm; hamnlederna har brytpunkter
  (`Lane.via`) så att fartygen går genom grindens mitt. Patrullbåt (`PatrolBoatAI`): ping 196 dB
  (~0,5 nm under skiktet, ~1 nm över), 6 kn, ping var 45:e s i patrull, master inom 2 nm med 1 %/s,
  skärm 1,5–2,5 nm ut. Ett fartyg på väg in inom 6 nm från grinden eskorteras (`escort`, 0,4 nm
  framför) till grinden. Jägare tar aldrig emot ett datum utanför `leash_nm` (gäller även Jagade).
  Förtöjda fartyg (`moored`) driver inte.
- Navigatören `följ S-3`: styr på kontaktens bäring var 15:e s och håller plottets fart (tills
  kaptenen sätter farten själv); `kurs` avbryter.
- Sundet (`sundet`, `strait_scenario`), 7 h, ett fartyg in efter 45–75 min, sedan 0,6/h in och ut
  i lotsfart (6–8 kn). Grindtricket: vänta söder om grinden, `turbin, djup 40, följ S-x` när
  fartyget passerat 0,2–0,45 nm, foto innanför, följ ett utgående fartyg ut. 8 frön: bot med bara
  besättningens verktyg klarar 3 (goda bilder i 6), bot som läser sanningen 5 (bilder i 8);
  ja-boten och den som försöker smyga genom skärmen utan fartyg klarar 0. Botarna i scratchpad
  (`follow_bot.py`, `strait_bot.py`).
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
