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
uv run main.py [--seed N] [--scenario kuba] [--tyst]   # spela (utan --scenario: huvudmenyn)
uv run pytest -q              # snabba tester, parallellt (~8 s; 12 s på 4 kärnor)
uv run pytest -q --slow       # alla, även hela spel och statistik (~1,5 min; 4 min på 4 kärnor); före commit
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
- **Uppdragsmål** (`sim/goals.py`, sanning): scenariot lägger `Goal`-objekt i `World.goals`
  (`StrikeGoal`, `PhotoGoal`, `ReportGoal`, `SurfaceNearGoal`, `EscapeGoal`, `TrainingGoal`,
  `GroundingFails`, `NoDiveInFjord`); `World._check_outcome` prövar dem i `RANK`-ordning, efter
  sänkt neutralt/alla fiender och före `forced`/`patrol_end`. `World.goal(cls)` hittar ett mål.
  `World.mission` håller bara det som hänt (sänkt, `best_photo`, `last_report_t`, `grounded_t`,
  räknare). Nytt mål = ny klass i `goals.py`, `World` ändras inte.
- **Importgränser** vaktas av `tests/test_import_boundaries.py`: kunskapsmodulerna når aldrig
  sanningen (importer under `TYPE_CHECKING` räknas inte), `sim/` importerar aldrig Textual.
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
- **Konvoj i plottet** (`zigzag.py`, kunskap): vid varje målmanöver sparar plottet benets sista
  lösning ≥ osäker (`ContactTrack.legs`, `turns`). Baskurs = viktad rak linje genom benlägena
  (σ läge + 0,8 nm sicksack), farten = median av benens fart längs baskursen; kvalitet ur σ och
  tak efter antal ben (2 ben ⇒ högst osäker, 3 ⇒ god). Benlängd = median av gap per kontakt.
  Gruppering: ≥ 2 icke-jagare inom 3 nm, ±30°, ±4 kn; jagare inom 5 nm är eskort. `ConvoyAssessed`
  ⇒ `Knowledge.convoy`. Konvojens girar sägs som `plot.convoy.turn`, inte `plot.maneuver`.
  Med periskoptitt var 4:e min: baskurs inom 5° och säker efter ~10 ben; bara sonar: grov fart
  (TMA drar avståndet mot 6 nm), kvaliteten dålig/osäker.
- **Anfall** (`anfall S-x`, navigatören, `firecontrol.approach`): kurs till en punkt 1,2 nm vid sidan
  av målets väg (konvojens baskurs om ≥ osäker, annars nuvarande ben eller TMA-lösningen) där målet
  är tvärs 4 min efter att vi är framme; omräkning var 30:e s. Hinns det inte i vår fart föreslås
  lägsta fart som räcker (inom 1,5 h). I skjutläge (tvärs inom 8 min, ≤ 2,5 nm från vägen) föreslås
  fart 3. Passerat (bakom, två gånger i rad, säkert bara med baskurs eller < 3 nm) ⇒ slutar.
  Torpedrummet (`_leg_warning`) varnar när gångtiden är längre än det som är kvar av benet.
  Fyra provkörningar (periskop var 4:e min): framme i alla, närmaste passage 0,2–3,3 nm.
  Besättningen visar vägen (aldrig avfyring): navigatören (`_convoy_watch`, var 30:e s) föreslår
  `anfall S-x` när plottet har konvojen, eller ett ensamt stort fartyg med färsk lösning ≥ osäker, och
  vi ligger framför (inte jagade, inte inom 20 min efter skjutläge, var 5:e min). Vakthavande föreslår
  `periskopdjup` och sedan `periskop S-x` var 4:e min när konvojen är känd eller sonar hör stora fartyg
  (`is_big_ship`: klassning stort/transport/tank, inte civilt), utom när vi är jagade, en klassad jagare
  är < 3 nm enligt plottet eller radarn varit mycket stark senaste 5 min. 8 frön, ja-boten: framme i
  4 (förut ~2); ja-boten som skjuter `salva` när navigatören säger skjutläge sänker 1–2 (förut 0).
- **Korta varianter** (`Scenario.warmup`, `Warmup(seconds, pilot)`): `Game` kör vakten före kaptenen
  med en fast plan (`pilot(game, t)` ger order via `game.command`) innan spelaren tar befälet, så att
  plott, sonar och bestick byggs av sensorerna (aldrig inskrivet). Rapporterna syns inte: gränssnittet
  skapar `Game(..., warm_up=False)`, kör `game.warm_up()` i en tråd medan ordern skrivs ut och
  prenumererar först efteråt. Loggboken börjar vid överlämnandet. `Handover` ⇒ vakthavande säger
  `off.briefing` (konvoj, kontakter, besticket ur kunskapen). Tidsgränsen är `World.patrol_end`
  (uppvärmning + speltid). Piloten kan lämna över tidigare genom att returnera True (`seconds` är
  då ett tak). `ScenarioDef.minutes` visas i väljaren. Kort variant = egen nyckel
  (`konvoj-kort`) som bygger på det långa scenariot. Alla scenarier har en kort variant (`-kort`, `-mot`,
  `-in`, `-ut`). Ny kort variant: provkör 8 frön med passiv bot, ja-boten och en bot med besättningens
  verktyg; riktmärken: första förslag eller kontakt inom 3 min, ja-boten ~2–4 av 8 (utom där följandet
  är kaptenens sak), viktiga lösningar ≥ osäker vid överlämnandet. Siffrorna under Kalibrering.
- **Övningen** (`ovning`, `training_scenario`): 8 okt 1962, 10:00, ytläge med bryggan bemannad i
  Kolafjorden utanför Poljarnyj, kurs ut, 10 kn. Botten `kola_seabed` (`seabed.Fjord`: land söder om
  kusten utom längs en fjord efter `path` med `half_w`/`depth` per punkt, holmar nära stranden minst
  `ISLAND_CLEAR_NM` från mitten, `in_fjord`); mynningen ~7,7 nm norrut, 260–340 m utanför. Farleden
  (`Scenario.fairway` ur sjökortets fjord ⇒ `Knowledge.fairway`/`fairway_to`, ritas `╌`). Navigatören
  (`farleden`, goal "fairway") styr 0,15 nm till styrbord, gir 0,25 nm före brytpunkten, säger
  `nav.fairway.done` (fritt att dyka) och föreslår `kurs mot övningsområdet`; föreslår `farleden` i
  fjorden (var 10:e min). Landvarningen tiger om landet ligger bortom girpunkten. Fix från bryggan
  (`_bridge_bearings`: ytläge, bemannad, land i sikte): ingen mast, ingen fartgräns, var 3:e min av sig
  själv, rättelse < 0,15 nm sägs inte. Trafik in/ut med brytpunkter 0,2 nm till styrbord.
  Övningsområdet 4,5 nm norr om mynningen, 1,5–2,5 nm vid sidan av leden; botten 350–420 m.
  Övningsledaren (`stations/training.py`, `TrainingOfficer`, roll vakthavande, tyst utan
  `Scenario.training`): stegen `dyk` (fart 6, periskopdjup), `svep`, `fix`, `framme` (fart 4), `djup100`,
  `provdjup` (300 m, bara där kortet visar ≥ 340), `smyg`, `lyssna`, `torped`, `pd`, `upp` (bara med en titt
  ≤ 2 min gammal och inget fartyg < 1,0 nm). Varje steg föreslås som ja-order med förklaring, bockas av ur egna
  instrument, navigatörens fix eller periskopbilden; 30 s paus mellan stegen. Stegen `framme`–`lyssna`
  görs i övningsområdet (inom 1,5 nm, kvar tills 3 nm; utanför föreslås kurs dit); inget föreslås förrän kortet visar oss 0,5 nm utanför
  mynningen. Klart ⇒ `train.done` och `TrainingGoal.done_t` (+30 s) ⇒ `training_done`.
  Dykning i fjorden (`Scenario.no_dive_in_fjord`): navigatören varnar (`nav.fjord_dive`), sanningen
  avbryter om djup > 3 m 0,2 nm innanför strandlinjen (`dived_in_fjord`). Grundstötning i mer än 2 kn
  (`mission["grounded_t"]`, sätts alltid) avbryter med `fail_grounding` (`grounded`). Ingen kort
  variant än. Passiv kapten går på grund i första böjen (~17 min).
  Lyssningsövningen: bevakningsfartyget SKR-112 (`exercise.py`, typ `guardship`, 132 + 1,25·fart dB,
  `side="neutral"`, ingen radar, `ExerciseShipAI`: raka ben 2,5–4,5 nm i 9–12 kn inom 3 nm från
  området). Klassat "bevakningsfartyg" ⇒ `ContactTrack.friendly` (inget hot: inga förslag om att
  gömma sig, ingen torpedberedskap; plottet räknar ändå på det, men föreslår TMA-girar bara medan
  `Knowledge.listening`, händelsen `ListeningExercise`). Steget `lyssna` (djup 40) klart efter minst
  8 min med lösning ≥ god, eller avbrutet efter 25 min. Sedan undervattenstelefonen
  (`exercise.partner_report`, en sensor, ≤ 5 nm, partnerns läge σ 0,1): kurs, fart och läge mot
  plottets lösning ("stämmer" om kurs < 20°, fart < 4 kn, läge < max(0,5 nm, 30 % av avståndet)).
  Förslagsveto (`Station.vetoes`): navigatören stoppar alla dykförslag där ordern förbjuder dykning;
  i ytläge föreslår maskin ingen smygmotor och navigatören inte botten.
  8 frön, ja-boten: klar i alla på 110–121 min (omkört 2026-11-15; förut angivet 92–106, före
  torpedsteget), ingen grundstötning; lyssningen 7–25 min, avbruten i 1 av 8 (förut 8–16), plottets
  kurs inom 7° i alla, läget 0,1–1,4 nm fel (efter ändrade gränser stämmer fler än 4 av 8).
  Övningstorped (`TORPEDO_TYPES["övning"]`, 53-61 utan stridsspets, 12 m djup): detonerar aldrig,
  noterar närmaste passage per fartyg (`Torpedo.passed`), sätter inte `hostile_act`; torpedrummet
  frågar inte om bekräftelse mot vårt eget fartyg och säger skjutlösning på det bara med
  övningstorped i tuben och medan torpedsteget pågår (`TorpedoExercise` ⇒ `Knowledge.torpedo_exercise`). Övningens beväpning ur `Scenario.armament` (tub 1–2 övningstorped,
  inget att ladda om ⇒ inga omladdningsförslag). Steget `torped` har ingen order: vakthavande går
  igenom (`train.torpedo.brief`, var 5:e min) och kaptenen beordrar själv; klart en minut efter
  beräknad passage, eller hoppas över efter 15 min utan avfyring. Partnern svarar på
  undervattenstelefonen (`exercise.torpedo_report`): träff = under kölen (halva längden), annars
  avstånd i meter. 8 frön, bot som skjuter en torped när lösningen är god: klar på 99–121 min,
  träff i 4, bom på 140 m i 1, långt bom (830 m, eller torpeden hördes aldrig) i 2, ingen avfyring i 1
  (omkört 2026-11-15; förut träff i 2, bom 70–90 m i 4).
  Kort variant (`ovning-kort`, 40 min): start på periskopdjup 4 kn inom 0,4 nm från
  övningsområdet, vakt 4 min (periskopsvep, fix), stegen från `djup100`, tidsgräns 60 min.
  8 frön: första förslag efter ~67 s; ja-boten klar på 41–53 min i 7, tiden ute i 1 (torpeden hoppas
  över); bot som skjuter klar på 22–52 min, träff i 3 (omkört 2026-11-15; förut 35–51, 25–37 och
  träff i 1); passiv kapten: tiden ute.
- **Land skymmer** (`World.land_between`, prov var 0,05 nm): ljud genom land +60 dB (`land_loss` i
  `tl_to_own`, jagarens och US-ubåtens `_tl`), bryggan och periskopet ser inte fartyg bakom land.
  Djupgående i ytläge 7 m (`SURFACE_DRAFT_M`): ytläge kan gå på grund. Med bryggan bemannad föreslår
  vakthavande inget periskopsvep och sonar ingen fart 4; i ytläge föreslår maskin inget om kavitation.
- **Radion och telegrammen:** allt radion tar emot publiceras som `TelegramReceived` (text, `kind`
  telegram/broadcast, mottagningsnummer ombord) ⇒ `Knowledge.telegrams`. Radiomannen säger bara att det
  kommit (`radio.message`, `radio.moscow`: `data["telegram"]` = numret, texten i `data["text"]` och
  `read_aloud`, som svenskt tal läser efter raden); loggboken skriver remsan under raden
  (`ui/strips.py`, `TelegramStrip`, bryts efter loggens bredd, högst `MAX_W`). Ordern är loggens första
  remsa (`SubApp._log_order`, kind "order"). `telegram` öppnar loggboken (`LogScreen(telegrams=True)`,
  alla fönsterstorlekar) med bara remsorna; mellanslag växlar till hela loggen, `logg` likaså. Radio Moskva (`sim/broadcasts.py`): `lyssna radio` på antenndjup
  (masten fri, radion hel) ⇒ efter `LISTEN_S` (20 s) säger radiomannen en sändning för orderns datum
  (`order_day` ur `DATUM:`-raden, `broadcasts_for`); bara stämning, aldrig information. Den 28 okt bara
  bärvåg. Ljudet `shortwave` (menyns ratt och brus) före rösten.
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
  rastrerar (en rad = två kolumner i höjd). Linjer (spår, djupkurvor, kust, farled streckad, bäringar,
  vektorer, osäkerhetsringar streckade) ritas i braille i prickskiktet `ui/canvas.DotLayer` (prickkoordinater
  2 per kolumn, 4 per rad); märken, etiketter, rutnät och gräns är hela tecken; högst lager vinner per ruta.
  Nytt system ritar sig självt.
- **Ubåten** (`ubåt`, även `profil`/`system`; `ui/boat.py`, `ui/boat_render.py`): djupprofilen och
  systemtavlan i en vy. Genomskärningen överst (från `HULL_MIN_H` rader, annars avdelningarna som lampor
  på andra rubrikraden), profilen till vänster (60 %) och panelerna till höger; under `SIDE_MIN_W` (110)
  profilen över panelerna (högst halva höjden). Panelerna kompakta (`render_compact_panels`): fara och
  varning först och fullt, lugna paneler fälls efter `FOLD_ORDER` (torpedrören sist) till en gemensam rad
  sist, och räcker inte det visar de oroliga bara sina larm.
- **Djupprofilen**: `Station.profile_items()` ger element (`sim/profile.py`):
  fasta djup (`Level`), navigatörens djuplogg (var 10:e s), ekolodets bottenlodningar
  (bara efter `ekolod`), isekolodets lodningar och sonarrummets hörda ljud. `Game.profile()`
  samlar, `ui/profile_render.py` ritar sidovyn (tid vågrätt, botten i eget band under
  bruten axel; vårt djup, kortets botten och tunna nivåer i braille vid exakt djup) och djupmätaren bredvid loggen. Tab växlar (hytten, när starpom har befälet) → logg → sjökort → ubåten → periskopbild → logg, med luckan öppen brygga före
  periskopbild (`SubApp.tab_views`; `VIEWS` är alla vyer).
- **Centralen** (`ui/central_render.py`, `CentralView` i `ui/widgets.py`): bild av центральный пост.
  Huvudvyns layout efter fönstret (`GameScreen.on_resize`, klasserna `big`/`narrow`): minst 120 × 36 ⇒
  centralen fyller vyn (`#central-big`, inga figurer), loggen är en remsa (11 rader) med djupmätaren bredvid och hela
  loggen är en egen vy (`LogScreen`, `ui/logview.py`: först i Tab-ordningen, `logg`; `central` tillbaka;
  slutrapporten öppnar den). Mindre ⇒ loggen stor och en liten central (40 × 13) ovanför djupmätaren;
  under 100 kolumner bara djupmätaren. `ReportLog.emit` sparar raderna (`entries`) och speglar dem till
  loggvyn (`mirror`); skriv aldrig loggrader med `write`. Bilden ritas i widgetens storlek (`Geometry`:
  mätarna växer med höjden). Från 100 × 22 (`BIG`, `Geometry.slots`) är väggarna instrument i braille
  (`ui/canvas.py`: `Braille` 2 × 4 prickar per ruta, stil efter prioritet; `ui/instruments.py`: `Dial`,
  `draw_dial`): gyro, sidroder (±35°), telegraf (handtag = beordrad fart, gul visare = maskinens svar),
  djup 0–500 m med prov- och krosszon, fart 0–30 kn med kavitationszonen (6 + djup/25), klocka, djuproder
  med libell. Avläsningen är exakt; visarna följer med tröghet (`Needles`, τ 0,5 s, kursen den korta vägen)
  och ritas tio gånger i sekunden (`CENTRAL_EVERY_S`, bara när huvudvyn syns). Under `BIG` de små
  lådmätarna. Ren funktion `render_central(status, speaking, t, width, height, shown)`
  ur `StatusSnapshot` (bara egna instrument) och vem som rapporterat senaste 3 s (`SubApp._spoke`, roll ⇒
  plats eller snabbtelefonens lampa). Mätare kurs/sidroder/djup/djuproder (rodren härledda ur beordrat mot
  verkligt), periskopet hissas med `periscope_up_s`, stegen och luckan (himlen syns), maskintelegrafen,
  julgranen (lucka, periskop, master), rött ljus på natten eller jagade (`night`, `hunted`), larmlampor,
  rök och vatten.
- **Systemtavlan**: `Station.system_items()` ger element (`sim/systems.py`):
  `Gauge` (panel, etikett, text, tillstånd ok/info/av/varning/fara, ev. stapel), `Compartment`
  (nio avdelningar, maskin), `TubeRack` (torpedrum), `Flooding`. Ur egna instrument
  (`own.sys`), aldrig om fienden. `Game.systems()` samlar, `ui/systems_render.py` ritar
  genomskärningen (skrov, torn, skott och vatten i braille, `HULL_ROWS` rader; avdelningarna som text) och panelerna (okända paneler hamnar sist, så nytt system ritar sig självt).
  Ryska skyltar (`ui/placards.py`): panelerna efter stridsavdelning (`PANEL_RU`: БЧ-5, БЧ-1 …, utelämnas när
  de inte får plats), vyernas rubriker (`view_title`, `VIEW_RU`: svenskan först) och mässingsskylten
  ЦЕНТРАЛЬНЫЙ ПОСТ i centralens tak när det finns plats före stegen. Ny panel eller vy: lägg till där.
- **Bryggan** (`stations/bridge.py`, `BridgeWatch`, roll vakthavande): tornluckan är sanning
  (`OwnSystems.bridge`: shut → manning 20 s i ytläge → manned → clearing 20 s vid order att dyka → shut);
  `OwnShip.bridge_open` håller djupet (depth_rate 0). Utkiken är en sensor: varannan sekund medan bryggan
  är bemannad `BridgeSighted` med en `PeriscopePicture` (eye "brygga", 8 m, ingen sektor) ⇒
  `Knowledge.bridge` (None vid utrymning). Bäring σ 1°, avstånd med ögat σ 15 % + 0,05 nm, kurs `AOB_SIGMA`,
  fart σ 3 kn; felen dras om var 60:e s per föremål (bilden fladdrar inte), och då får plottet en
  observation (`source="brygga"`). Egen `random.Random` så att resten av spelets dragningar inte flyttas.
  Ropar ut nytt eller > 5 min ur sikte; flyg i sikte eller jagare < 3 nm ⇒ förslag `djup 60`.
  Sonar skriver inte över en bättre klassning (utkikens GOD) med sämre.
  Vyn (`ui/bridge.py`, `ui/bridge_render.py`, `brygga`): 120° synfält åt `view_rel` relativt fören (← → 15°,
  mellanslag förut), himmel (moln/stjärnor), horisont, sjö med vågor fasta i världen som driver med tiden,
  fördäck förut och kölvatten akterut, räcket nederst (land, vågkammar, moln, reling och kölvatten i braille i
  `_Grid.dots`, som periskopet delar); föremål ritas med periskopets `_draw_object`
  (siluett, lanternor, flyg, is), längre bort än 8 nm bara ett tecken. Bäringsskala, 360°-remsa
  (`render_strip(window=...)`) och datarad om föremålet närmast blickens mitt (±12°). Utan bild säger
  vyn varför ur `StatusSnapshot.bridge` och djupet.
  Utkiken ser också land (`LandBearing` var 3:e grad: strålar mot `seabed.depths` ≤ 0 ut till sikten,
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
  då får plottet en observation (bäring σ 0,5°, avstånd 8 % + 0,03, `AOB_SIGMA`, fart 2). Nytt i
  okularet ropas ut en gång per hissning. Egen `random.Random`. Övningsledaren räknar bara `live=False`.
  Kikaren (`optic` "kikare", ytläge med bemannad brygga): samma order men ingen mast, ingen fartgräns,
  bilden är bryggans (`Knowledge.bridge`) inom synfältet, inga egna utrop eller plottobservationer
  (`off.binoculars.*`); fälls när bryggan utryms. I ytläge gäller ingen fartgräns för masten.
  Periskopvyn med bemannad brygga och nere periskop visar bryggans levande bild ("KIKARE, bryggan");
  blickens sanna bäring delas med bryggvyn (`SubApp.look_bearing`). Utryms bryggan blir dess sista bild
  `Knowledge.periscope` om den är nyare. Samma fartyg utan ändring (kurs < 15°, fart ≤ 3 kn) inom 5 min
  efter förra utropet: `off.periscope.again`. Hålläge > 60 s med ett hot i plottet: vakthavande föreslår
  `periskop ned` (var 3:e min).
- **Periskopbilden** (`sim/periscope.py`): `Knowledge.periscope` håller den senaste bilden. Synlig del (helt/överbyggnad/mastoppar) ur ögonhöjd (periskop 1,5 m, brygga 8 m)
  och `HEIGHTS`; kursbedömningens σ (`AOB_SIGMA`) följer synlig del, natt = bara lanternor (σ 25°).
  Vinkel på bogen `aob` + styrbord. Fartyg bär plottets beteckning, aldrig sanningens id.
  Vyn (`ui/periscope_render.py`, `ui/periscope.py`): 360°-remsa med fören i mitten, okular (32°; kanten,
  vågkammarna och kikarens land i braille, `draw_land` delas med bryggan);
  masten uppe (`StatusSnapshot.periscope`/`periscope_train`/`periscope_up_s`): okularet står mot
  periskopets bäring, ← → vrider 5° (`vrid periskop`, `Order.INSTRUMENT`: inte i loggboken), mellanslag
  förut, ↓ ned; nere: mot valt föremål (← →), ↑ `periskop upp`; siluetter i `ART` (fören åt höger, speglas vid babord, trycks ihop efter
  |sin vpb|, skärs efter synlig del), natt bara lanternor, bild äldre än 60 s nedtonad.
  Där okularet inte varit under hissningen följer föremål med från bilden före i 10 min (`seen_t`,
  ritas nedtonade); i ett svep eller en titt räknas allt som setts som sett nu.
  Is: `ice.ice_view` (periskopet är en sensor) ger kant och vallar i 16 riktningar ut till 0,6 nm;
  kommer masten inte upp för isen publiceras `PeriscopeBlocked` och vyn säger det.
- **Starpom** (`stations/starpom.py`, `FirstOfficer`, `Role.XO`, Sokolov, kapten 3:e rang): `starpom har befälet`
  ⇒ kaptenen i hytten; starpom svarar på förslag via `Station.on_suggestion` (Game frågar stationerna efter
  leverans; sant = beslutat) och ger ordern med `game.command(order, by="starpom")` (`OrderIssued.by`, räknas
  inte i loggboken). Mandat `MANDATE` (orderklasser; aldrig avfyring, salva, sändning, ytläge, avbrott,
  aktiv sonar, radar, foto) plus det ordern lägger till (`ORDER_MANDATE` efter `Knowledge.order_tasks`, ur
  `Scenario.tasks`: patrull, rapport, anfall, foto, ut, station, övning; testat mot målen): anfall ⇒ `anfall S-x`.
  Han väger förslag mot ordern (`_objection`, fasta regler, inte vid larm eller jakt): nej (`xo.decline`) till
  styrorder från andra än navigatören medan navigatören anfaller eller följer, och djupare än antenndjup när
  ordern kräver rapport och radion behöver masten. Med anfallsorder ropas kaptenen (fara) 2 min + gångtiden före
  navigatörens `attack_eta_t` och när ett klassat stort fartyg med färsk lösning ≥ osäker är < 3,5 nm
  (`_target_watch`); `nav.attack.arrived` är fara; radions förvarning ringer när ordern kräver rapport. Väckning (`_wake`): info = lampan (civil kontakt, `plot.maneuver`, ny kontakt),
  fråga = telefonen ringer (hotkontakt med lösning ≥ osäker, stort fartyg, konvoj, telegram, förslag utanför
  mandatet, tidsgränsen 15 min, `väck mig`, larm i `ALARM_LEVELS`; samma fråga högst var 10:e min; ordonnansen
  efter 20 s), fara = högtalaren (`alarm_level` "danger": övriga larm, jakttecken) ⇒ 1× och kaptenen går (40 s,
  `Station.intercept` stoppar hans order under tiden) och får lägesrapport (`xo.handback`, `officer.situation`).
  `tid 30`/`60` bara med starpom i befäl; `sov` ⇒ 60×. Status: `StatusSnapshot.command`, `captain_at`, `walk_s`,
  `phone`, `sleeping` (via `Station.status_fields`). Vyn `hytt` (`ui/cabin.py`, `ui/cabin_render.py`: från 64 × 18 sedd från kudden i perspektiv,
  dörren längst bort till höger, `_Room`; på skottet rivkalendern för orderns dag
  (`StatusSnapshot.order_day` via starpom, nästa blad vid midnatt), fotot av hans första ubåt, diplomet,
  medaljerna och familjen så långt platsen räcker; ljuset (`_shade` färgar om varje ruta: natt ⇒ bara
  nattlampan, telefonens sken gult/rött på skottet, rök dämpar), ögonlocken när han sover (`lids_of`, öppna när
  det ringer), andningen, taklampan och mössan svänger (`sway_of`: jagade, sjön nära ytan, krängning i gir),
  damm från rören när vi är jagade och dis av rök; dörren (`StatusSnapshot.door` ur starpom: `steps` fötter i
  ljusstrimman 4 s före ordonnansens knackning, `ajar` 12 s med honom i springan, `open` de första 4 s när kaptenen
  går, sedan gången); mindre fönster den enkla bilden) öppnas
  av sig själv (`SubApp._follow_command`) och står först i Tab-ordningen; visar bara starpoms och telefonens
  rapporter, Enter svarar. Ljudet i hytten (`ambience.muffled`, `audio.from_central`): båten ×0,55, mumlet
  svagt, inga hydrofonljud eller sväv, centralens repliker tysta (larm hörs); telefonen `phone`, knackning
  `knock`. 8 frön (`kalibrering/starpom.py`, kaptenen lämnar över igen efter 10 min lugn): inga order utanför
  mandatet, utfallen som ja-boten (kuba 8 patrol_end, konvoj 8 convoy_missed); kuba 3–12 ringningar och 0–2
  fara på 3,5 h, konvoj 6–20 och 0–4 på 1–3 h. Efter ordern i mandatet (2026-11-16; kaptenen går till centralen
  när starpom ber om hans beslut): kuba-kort rapporten i 5 (ja-boten 4; förut 0, ingen sände), med `salva`
  (kaptenen skjuter bara i centralen) konvoj 3 sänkt och 1 neutral (vaken salvakapten 3), konvoj-kort 1 (1);
  utan starpoms rop före skjutläget och vid stort fartyg < 3,5 nm var konvoj 0. Nej i 5 av 40 körningar (1–4 st).
- **Huvudmenyn** (`ui/menu.py`, `MenuScreen`): uppdragen grupperade (`mission_groups`: kort variants nyckel
  = lång nyckel + "-x", titeln "Rubrik – variant, datum", det långa först, `FIRST_GROUPS` övningen först),
  rubriker är avstängda alternativ, beskrivningen (`brief`) bredvid, sist Inställningar, Order och
  ordlista, Avsluta. Inställningar (`ui/settings.py`): ljud, talets språk, slumpfrö (`SubApp.sound_wanted`,
  `language`, `fixed_seed`; `--seed`/`--tyst` sätter startvärdena, fröet gäller alla uppdrag tills det
  ändras). Order och ordlista (`ui/manual.py`) hämtar orderna ur stationernas `COMMANDS` per roll. Nytt scenario hamnar
  i menyn av sig självt om nyckel och titel följer mönstret. Stämningen (`ui/menutext.py`): sidhuvud som
  hemlig handling på rött fält (ryska med svensk översättning), stämpel per uppdrag efter datumet
  (`stamp_for`: övning ДСП, före 22 okt СЕКРЕТНО, 22–26 СОВ. СЕКРЕТНО, 27– ОСОБОЙ ВАЖНОСТИ), fjärrskrivarremsa
  (`DISPATCHES`, `ticker_at(t)`: kalendern 1–28 okt, 24 tecken/s, börjar om) och stridsberedskapen i
  sidhuvudet efter meddelandet (ständig, höjd, krigsfara, full; de två sista blinkar). Den 28 okt följer
  spelets historia: kriget har börjat. Färger ockra/flaggrött (`BG`, `INK`, `RED` …), även inställningar och
  ordlista. Ljud (`ui/menu_audio.py`, `MenuSound`, bara med ljudet på): egen musik (kör i d-moll, hjärtslag
  i basen, klocka, horn andra varvet; 64 s), hamnen (vind, vågor, mistlur, knarr; 40 s) och fjärrskrivaren
  medan remsan skriver; slingorna är cirkulära (efterklangen viks runt). Syntesen (~2 s) i en tråd,
  `lru_cache`. `MenuMixer` (en `Ambience` med `extra`-kroken) lägger enstaka ljud ovanpå. Uppdrag valt ⇒
  `depart()`: telegrafklockan, musiken tonar bort, fjärrskrivaren låter medan ordern skrivs ut; stängs när
  kaptenen tar befälet. `ctrl+t` och Inställningar slår av och på (`SubApp.menu_sound_sync`).
  Radio Moskva (`BULLETINS`, `radio_at(t)`): påhittade sändningar efter 25 s och sedan var 95:e s, allt
  mer olycksbådande (den sista upprepas); remsan visar översättningen. Ljud: ratten (`synth_tuning`),
  kortvågsbrus, musiken sänks; rösten är Milena via `say -o` genom `radio_voice` (smalt band, fading).
  Utan Milena bara brus. Bilden (`ui/menu_scene.py`, `render_scene(cols, rows, t)`): К-114 vid kaj i
  braille under beskrivningen (10 rader, bara när fönstret är ≥ 34 rader): stjärnor, fjällen, kajen med kran
  och lampa, ubåten med röd stjärna och lanterna, glitter på vattnet, snö i vinden; ingen slump (`_hash`). Flödet: menyn → spelet (`GameScreen` i `ui/app.py`, vyerna ovanpå) →
  huvudmenyn. `SubApp` håller spelet, ljudet och inställningarna (ljud, talets språk) över uppdragen;
  widgetarna nås med `app.gs().query_one(...)` (`app.query_one` ser bara standardskärmen). Efter
  slutrapporten går vyerna att titta på; Enter med tom orderrad (även i en vy) ⇒ `return_to_menu()`:
  timern stoppas, ljud och sanningslogg stängs, `game = None`, menyn markerar scenariot. Nytt uppdrag =
  nytt `Game`, ny buss, nytt frö om inget är inställt, logg `truth-<tid>-<frö>.log`.
  Den hemliga ordern (`ui/telegram.py`) visas som chiffertelegram: `order_header` (ШИФРОГРАММА, mottagningsnr
  ur fröet, uppdragets stämpel, avsändaren ur orderns `FRÅN:`-rad via `staff_of`) och `order_signature` under
  texten när den är utskriven (`Teletype.header`/`signature`/`style`, ockra papper). Slutrapporten börjar med
  `report_header` (ДОНЕСЕНИЕ till samma stab, stämpeln; `ReportLog.add_ending(summary, header=...)`).
  `avbryt uppdraget`/`avsluta` ⇒ vakthavande frågar (`off.confirm_quit`, förslag `avbryt uppdraget
  bekräftat`), `ja` ⇒ utfallet `quit`.
- **Order i alla vyer** (`ui/viewbase.py`): vyerna ärver `ViewScreen` (rapportraden, `Esc`, orderrad
  `OrderLine` som visar väntande förslag). Vyns tangenter står i `EMPTY_KEYS` och gäller bara när
  orderraden är tom (Input tar annars alla utskrivbara tecken); bokstäver är aldrig vytangenter.
- **Tangenter:** `Tab` växlar vy, `Esc` tillbaka, `ctrl+t` ljud. Undvik F-tangenter
  (medietangenter på Mac) och ctrl-tangenter som orderraden (`Input`) redan använder.
- **Ljud** (`ui/audio.py`): `SoundBoard` lyssnar bara på bussen – `ReportDelivered` ger tal
  (`say`, takt per roll) och larm (`CUE_BY_TYPE`); `SoundHeard` (med sensorns `se`) ger
  hydrofonljud panorerade efter relativ bäring (`TRANSIENT_SOUND`); `OwnSoundMade` ger egna
  ljud (ping, avfyring, skenmål, nödblåsning). Syntetiserade wav. Av som standard i `SubApp`.
  Bakgrundsljud (`ui/ambience.py`): `ambient_targets(status, tracks)` ur `StatusSnapshot`
  (inkl. `sea_noise`, `fire`, `smoke`, `ventilating`) och hållna kontaktspår; `Ambience`
  mixar sömlösa slingor i en sounddevice-ström. Kontaktljudet följer klassificeringen.
  Centralen: `aircon` (alltid med reaktorn, svagare vid tyst gång), `crew` (mummel bakom skotten; tyst vid
  smygmotor eller jagade), `dread` (lågt sväv: jagade 0,11, hållen klassad örlogskontakt med se > 10 0,05).
  Skeppsklockan slår glasen (`bells_for`, 1–8 per fyratimmarsvakt) vid varje halvtimme på spelklockan,
  inte vid tyst gång eller jakt (`SoundBoard._ship_bell`). Vid överlämnandet läser vakthavande ett utrop i
  högtalaren (`crew_announcement` i `ui/telegram.py`: övning, operation eller krig efter stämpeln;
  `SoundBoard.announce`, ryska med Milena annars svenska; översättningen i loggen).
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
  Ärlig kvalitet (`tma.py`): processbrus för målets manöver q = 1 kn²/h (3 gav ofta bara osäker på
  två ben); utan nya bäringar sannolikheten τ/(τ + 10 min) att målet girat, σ 90° (en 10 min gammal
  lösning blir osäker); jagare som pingar medan vi är jagade q = 400 (inte i lugn patrull: då
  tappade plottet patrulljagaren och radion gick upp för tidigt); kursens σ ≥ 15/30/60° ⇒ högst
  god/osäker/dålig när målet går ≥ 3 kn. Brytpunktstestet räknar utan brus. Mot sanningen (ja-boten,
  övning/kuba/konvoj-kort/sundet, 8 frön): grova fel (avstånd > 50 % eller kurs > 90°) bland god/säker
  11 % ⇒ 9 %, fel > 3σ 18 % ⇒ 11 %; säkra lösningar med kurs > 90° fel 6 % ⇒ ~1 %. Det som är kvar är
  mest girar de senaste minuterna som plottet inte hunnit se. Mätskriptet: `kalibrering/tma_kvalitet.py`.
- Periskopet i TMA: varje titt ger, utöver avstånd (σ 8 % + 0,03 nm), kurs (`AOB_SIGMA` efter synlig del)
  och fart (σ 2 kn) som mätningar (`BearingObs.course_obs`/`speed_obs`). En titt vars kurs avviker mer
  än max(20°, 3σ) från lösningen före titten ⇒ målet har girat, TMA börjar om från titten
  (`PlotTeam._look_turn`). Konvoj, titt var 2:a min på 2–6 nm: lösningar säker hade läge median
  0,48 nm, kurs 39°, fart 3 kn fel; nu 0,23 nm, 7°, 0,9 kn (p90 0,5 nm, 41°: girar mellan tittarna).
- Civil trafik (Kuba, `KUBA_TRAFFIC` i `scenario.py`): tre leder, 1,8 fartyg/h plus 3 från
  start, 9–14 kn, källnivå `140 + fart`. Maskering: neutralt fartyg inom 4° av målets
  bäring adderar sitt brus; ubåt < 100 m inom 0,3 nm från ett handelsfartyg får −12 dB eko
  hos jagaren. Jagaren hittar ja-boten i ~5 av 8 frön, som utan trafik.
- Ubåtsjaktflyg (Kuba, `KUBA_AIR`): första plan efter 40–80 min, 60–90 min över kvadraten,
  45–75 min mellan. Radar: master 6 nm (6 %/svep), ytläge 25 nm. MAD 250 m snedavstånd
  från 60 m höjd (säkert under ~190 m). Passiva bojar DT 8; aktiv boj 205 dB var 20:e s.
  Med flyg: jagaren hittar ja-boten i 9 av 12 frön (7 utan), flyget självt i 8 av 12. Omkört
  2026-11-15 (`kuba_jakt.py`): jagaren 12 av 12, flyget 11 av 12, 338 sjunkbomber, skrovet skadat i 2.
- Botten (Kuba): djuphav 1 850–2 350 m, +15 m/nm norrut; bank 120–200 m med kanten 4,5–5,5 nm
  från väst- eller östsidan ⇒ ~15–18 % grundare än 300 m; berg med topp 250–400 m minst 4 nm
  från start; ränna 250–450 m djup. Kortets fel 0,5 nm (Arktis 0,8), berget saknas i 25 %.
  Arktis: slätt 3 300–3 800 m, rygg med krön 900–1 200 m ± 100–200 m.
- Jagare (alla scenarier): död zon under skrovet, ingen eko om horisontellt avstånd < djup/tan 20°
  (200 m ⇒ 0,3 nm), så en djup ubåt tappas i slutet av anfallet. Döv 60 s efter en detonation
  inom 1,5 nm. Jagare hör inte sina egna sidans pingar. Kuba efter detta: ja-boten hittas
  fortfarande 8 av 8, men jagaren tappar och återfinner kontakt 2–20 gånger (förut 1) och
  anfaller 1–19 gånger (förut 2–37).
- Sonarrummets takt: samma kontakts bäring ropas högst var 60:e s (`BEARING_MIN_GAP_S`), annars vid
  5° ändring eller var 5:e min. Pingtakt snabb vid ≤ 13 s, långsam först efter två mellanrum ≥ 20 s
  i rad (en missad ping vänder den inte). Jagade, ja-boten: ~5 rapporter/min under jakten (förut ~11).
- Sonar publicerar `HuntSigns` vid snabb pingtakt och plask; `Knowledge.hunted()` (5 min). Då
  föreslår maskin `eng.suggest.sprint` (turbin, djup ≤ 220 m, fart = kavitationsfart − 1)
  i stället för smygmotor, och sonar föreslår inte fart 4 när en kontakt tappas.
- Jagade (`jagad`, `hunted_scenario`): ubåten börjar 45 m, 6 kn, 1,3 nm från bankens
  300-meterskurva på djupt vatten; DD1 2,2–3 nm i norr med färsk kontakt (`start_hunt`), DD2
  7–8,5 nm i söder. Jagarna är `partners` och delar fix (σ + 0,4 nm). `escalate_after=3`:
  skarpa efter tre övningsanfall (~25 min). `leash_nm=1`: släpper jakten när datumet ligger mer
  än 1 nm utanför kvadraten. Mål `EscapeGoal`: 1 nm utanför och ingen jägare med datum
  inom max(1 nm, 3σ) från oss (ett skenmål räknas inte). Navigatören (`exit_route`) föreslår
  närmaste kant, +4 nm straff inom 40° från en hotkontakt, och sträckan där kortet visar grundare än
  300 m (`EXIT_DEEP_M`) räknas dubbelt: över banken kan vi inte springa djupt. 8 frön: passiv 0,
  ja-boten 6 (15 av 24), djupt och fort (turbin 12 kn, 200 m, navigatörens väg ut vid start, ja till
  djupförslag) 8. Utan grundstraffet gick vägen ut ofta över banken och ja-boten klarade 2 av 24
  (vilket förslag som kommer först beror på rapporternas slumpade fördröjning).
- Jagade kort (`jagad-kort`, `hunted_scenario(short=True)`): kvadraten 7 nm, ubåten 2–2,5 nm från
  djupvattensidans kant, DD1 1,4–1,7 nm bort i anfall, DD2 3–3,8 nm bort på djupvattensidan, båda
  skarpa från start; tidsgräns 30 min. 8 frön: passiv 0, ja-boten 4 (24–26 min), djupt och fort
  (navigatörens `exit_route` var 60:e s) 6 (19–27 min). Sonar hör jakten efter 6–8 s.
  Medan vi är jagade (`Knowledge.hunted`) föreslår plottet inga TMA-girar, och maskinens sprintförslag
  har alltid med `turbin` (förslaget levereras sent).
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
  besättningens verktyg klarar 3 (goda bilder i 6; omkört 2026-11-15: 5, bilder i 7), bot som läser
  sanningen 5 (bilder i 8; inte omkört);
  ja-boten och den som försöker smyga genom skärmen utan fartyg klarar 0. Botarna i scratchpad
  (`follow_bot.py`, `strait_bot.py`).
  Väntläget (första steget, `_harbor_watch`/`_wait_point`): före fotot och utanför nätet föreslår
  navigatören `smygmotor, väntläget`: 1,4 nm ut från nätet åt det håll kortet visar djupast vatten
  (farleden), 0,35 nm vid sidan åt vår sida, ≥ 40 m på kortet; ritas som känd plats `Väntläget`.
  `väntläget` styr dit (5 kn, 3 kn inom 5 nm från nätet) och håller läget i 1–2 kn; `kurs` eller `fart`
  avbryter. Resten (följ, foto, ut) föreslås inte. 8 frön, bara detta förslag: framme i 8 efter
  ~100 min, första fartyget in passerar 0,1–0,6 nm (oftast 0,3–0,55); patrullbåten får kontakt
  under passagen genom skärmen i 7 (passiv bot 3), oberoende av djup.
- Sundet in (`sundet-in`, `strait_scenario(short=True)`): 06:20, vakt 10 min (`smygmotor, väntläget`),
  ubåten startar ~1,4 nm utanför nätet 0,35 nm vid sidan, ett fartyg på väg in 3,0–3,2 nm från nätet vid start
  (passerar väntläget 3–5 min efter överlämnandet), inga fler in. Mål `PhotoGoal`: foto minst god ⇒
  `photo_taken` (ingen utväg). Tidsgräns 35 min efter överlämnandet. 8 frön: passiv 0, ja-boten 0 (följandet
  föreslås inte, kaptenens sak), grindboten (`turbin, djup 40, följ S-x` när fartyget passerat 0,2–0,45 nm,
  `kurs mot ankarplatsen, fart 4, periskopdjup` 0,6 nm innanför, `foto`) 6, på 18–33 min.
- Sundet ut (`sundet-ut`, `strait_scenario(out=True)`): 07:00, startläget byggt direkt: innanför nätet 1,0–1,2 nm,
  0,2 nm vid sidan av farleden på periskopdjup; vakten (4 min) tar `foto` (bilden via bussen) och går till 20 m
  på smygmotor. Ett fartyg ut startar 0,9–1,2 nm bakom oss (passerar 3–6 min efter överlämnandet), inga fler.
  Ute = söder om `Scenario.escape_y_below` (1 nm söder om nätet) och ingen har oss; navigatörens väg ut räknar
  mot linjen. Tidsgräns 30 min. 8 frön: passiv 0, ja-boten 0, utboten (periskoptitt var 60:e s, `turbin, djup 25,
  följ S-x` när fartyget passerat 0,2–0,45 nm, efter 1,2 nm söderut fart 10) 5, på 16–22 min
  (omkört 2026-11-15: 5, på 20–26 min).
- Konvojen (`konvoj`, `convoy_scenario`): 28 okt, krig, 06:30 (dagsljus). Konvoj (2 trupptransporter,
  1 tanker) och 2 eskorter, baskurs 190–230°, start 16–20 nm bort, vägen passerar oss på 1,5–5 nm;
  ordern ger läge (±2 nm) och kurs avrundad. Mål `StrikeGoal`: minst ett mål sänkt och ingen
  jägare har oss 10 min efter senaste sänkningen ⇒ `convoy_attacked`; alla mål > 8 nm och förbi oss
  ⇒ `convoy_missed`. Kuba-trafik och flyg finns kvar. Träffradie för stora fartyg = halva längden
  (`HULL_HALF_NM`: transport 0,045, tanker 0,05 nm). Salva (`salva S-x`, `eld tub 1-3 mot S-x`):
  raka torpeder i solfjäder, avstånd vid målet = lägesfelet (σ avstånd, fart, kurs under gångtiden)
  inom 0,08–0,25 nm. Sonar håller isär okända pingare på en utjämnad bäring (grind 8° + 0,15°/s sedan förra pingen, högst 20°). 8 frön: passiv 0, ja-boten 0,
  bot med besättningens verktyg (periskop var 4:e min, `anfall`, salva mot klassad transport/tanker
  inom 3 nm, sedan djupt bort) 3 (och 1 neutral sänkt). Boten i scratchpad (`convoy_bots.py`).
- Konvojen kort (`konvoj-kort`): konvojen 13–15 nm bort, vakt 35 min (periskopdjup, fart 3, svep var
  4:e min), sedan 45 min. 8 frön: plottet har konvojen vid överlämnandet i alla, 5–9 nm bort, ingen
  eskort har oss; första förslag 0–3 min efter; ja-boten i skjutläge i 4 (9–34 min). Bot som skjuter
  `salva` (upprepad) mot klassad transport/tanker ≤ 3 nm med lösning ≥ osäker: sänker 1 på 28 min
  (samma bot i `konvoj`: 1, på 69 min). Uppvärmningen tar ~5–8 s. Efter plottets periskoprättelse:
  `konvoj` 2 av 8, `konvoj-kort` fortfarande 1 av 8 (omkört 2026-11-15 med `konvoj_salva.py`: `konvoj` 3
  av 8 på 57–60 min, `konvoj-kort` 2 av 8; `konvoj.py attack` 2 av 8); boten skjuter på gamla lösningar (titt var 4:e min,
  ben på 5–10 min). Öppen fråga: ska besättningen föreslå en titt strax före skjutläge?
- Konvojen motanfall (`konvoj-mot`, `convoy_counter_scenario`): ledpunkten 1–2 nm före tvärs, vi 1,8–2,4 nm
  vid sidan. Vakten (`_CounterattackWatch`): periskopdjup, titt var 60:e s, `salva` (två gånger) mot
  stort fartyg med lösning ≥ god, ≥ 60 s sedan senaste gir, titt ≤ 60 s gammal, fart ≤ 20 kn, ≤ 2,5 nm;
  överlämnar när torpedrummets gångtid − 45 s gått (2–4 min in) och sätter `patrol_end` +30 min. Har ingen
  eskort oss då ger närmaste eskort färsk kontakt (σ 0,1 nm, torpedbanorna). Eskortens koppel 6 nm.
  Eskorternas ping hittar oss på 1,3–1,9 nm även under skiktet, så att gömma vakten går inte.
  8 frön: vakten skjuter i 8, träff i 6 (25–155 s efter överlämnandet); passiv 3, ja-boten 4,
  djupt och bort (turbin 12 kn, 200 m, bort från hotet) 6 (omkört 2026-11-15: passiv 5, ja 5, bort 6).
- Eskorter (alla konvojer): en eskort med egen kontakt ≤ 40 s gammal och < 0,8 × den jagandes avstånd till
  datumet tar över jakten (`_closer_than`); i anfall går eskorten `SPEED_CLOSE` tills den är 1 nm från
  datumet (förut anfallsfart 15 kn hela vägen, så den hann sällan fram innan kopplet släppte).
- Kvadrat 7 kort (`kuba-kort`, `kuba_short_scenario`): jagaren 3–4 nm bort i patrull (övningsbomber), vakt
  15 min (smygmotor 3 kn på 100 m, gir +70° efter 7 min), sambandstillfälle 5 min efter överlämnandet i 15 min,
  sedan 10 min. Flyget efter 5–10 min. Mål `ReportGoal`: rapport sänd inom fönstret (`last_report_t`)
  och, när fönstret stängt, ingen jägare med datum σ ≤ 0,5 nm på oss (`_hunting_us(max_sigma=...)`; pejlingen
  av sändningen, σ 1,5, räknas inte) ⇒ `reported`; ingen rapport ⇒ `report_missed`. Radion (`report_required`):
  väntar (`radio.wait`) så länge plottet har en hotkontakt ≥ osäker närmare än 5 nm (`RADIO_SAFE_NM`), föreslår
  antenndjup när den gått längre bort (`radio.clear`), sedan periskopdjup och `sänd rapport` (inte när vi är
  jagade). Förvarningar under vakten ges igen vid överlämnandet. Sonar föreslår inte skiktet medan radion
  behöver masten (`RadioStation.needs_mast`), utom när vi är jagade. 8 frön: plottet har jagaren vid
  överlämnandet i 7, passiv 0, ja-boten 4 (rapporten sänd i 7).
- Provdjup 300 m, krossdjup 450 m, periskopdjup ≤ 18 m, antenndjup ≤ 30 m.
- Packis (`ice.py`): rutor 0,05 nm, flerårsis 2–4,5 m, kölar 8–25 m (6 % 30–45 m),
  170 råkar, 28 polynyor ⇒ ~4–5 % öppet vatten, en öppning ungefär var 30:e minut
  i 5 kn. Tornets topp 13 m och skrovets 8 m över kölen. Tunn is ≤ 1 m bryts i
  ≤ 2 kn på 40 s. Isdrift 0,25 kn mot 200°. Isbrus 50 dB (fast is) till 72 dB.
- Arktis: generatorn 142 dB, US-ubåt 125 + 1,5·fart med DT 0 och egenbrus 48 + fart.
  Mål: ytläge inom 1,5 nm från Nord-7. Ja-boten når målet i 9 av 12 frön (omkört 2026-11-15 efter
  plottets ärliga kvalitet; förut 7, ännu tidigare angivet ~10).
- Arktis kort (`arktis-kort`, `arctic_scenario(short=True)`): stationen 3,6–4,2 nm norrut vid start, vakt
  20 min (`kurs mot Nord-7, djup 60`), alltså 1,7–2,6 nm kvar vid överlämnandet; nödsignalens läge känt
  (σ 0,6). US-ubåten 5,5 nm från stationen vid start (2,5–5 nm från oss vid överlämnandet, oftast ohörd).
  Branden 5–12 min efter överlämnandet, tidsgräns 35 min. Navigatörens sökspiral runt stationen och
  maskinens förslag att ventilera vid en öppning tar inte över när vi är på väg upp (beordrat djup ≤
  periskopdjup). Uppstigning stilla ~0,25 m/s, därför 60 m. 8 frön: passiv 0, ja-boten 2.
- Brand (arktis, 40–110 min): rök 0,0009/s medan det brinner (7–13 min), sedan
  +0,2/h tills ventilation (−0,02/min på periskopdjup, −0,05/min i ytläge). Rök 1,0 = förlorad.
  Röken sänker `effective_skill()` med upp till 50 %.

## Arbetssätt
- Bygg i steg och **committa efter varje steg** (användaren vill det). Vid större
  nya delar: föreslå struktur och invänta ok.
- Nytt system ⇒ tester i `tests/`. Statistiska påståenden (TMA, sonar) testas över
  flera seeds, inte ett enda lyckat frö.
- Testerna körs parallellt (pytest-xdist, `-n auto` i pyproject; `-n0` för seriellt). Ett test som
  tar mer än ~1 s (hela spel, flera frön, uppvärmning, gränssnitt) märks `@pytest.mark.slow` och körs
  bara med `--slow` (`tests/conftest.py`). Kör `--slow` före varje commit. GitHub Actions
  (`.github/workflows/tester.yml`) kör `--slow` vid varje push. Scenariotestet hoppar över de korta
  varianternas uppvärmning utan `--slow`.
- Verifiera spelkänslan med en huvudlös genomspelning: skapa `Game`, prenumerera
  på `ReportDelivered`, skriv ut rapporter, kör `g.tick()` i en loop (gärna med
  en bot som svarar `ja` på förslag). Tillfälliga skript i scratchpad; botar som ger siffrorna under Kalibrering ligger i
  `kalibrering/` (se dess README) och uppdateras där.
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
