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
uv run --extra fonster fonster.py [samma flaggor]       # i eget fönster (textual-serve + pywebview, Dockikon)
sh ikon/bygg-app.sh [mål]                              # bygg K-114.app (standard ~/Projekt/Lokalt; ej installerad sedan 2026-11-21)
uv run python web/bygg.py                               # webbversionen (Pyodide) till web/dist, se web/README.md
uv run pytest -q              # snabba tester, parallellt (~18 s på 4 kärnor); före varje commit
uv run pytest -q --slow       # alla, även hela spel och statistik (~6 min på 4 kärnor); större steg
```

## Designprinciper (får inte brytas)
1. **Spelaren räknar aldrig själv.** Besättningen räknar och rapporterar.
2. **Varje bedömning har kvalitet** (`Quality`: dålig, osäker, god, säker) som
   härleds ur datan, t.ex. TMA-kovarians. Slumpa aldrig fram kvalitet.
3. **Sanning och kunskap hålls isär.** Bara sensorer (`sim/sonar.py`, och
   periskop/radar/aktiv sonar i stationerna) läser `World`. `Knowledge` byggs
   enbart från händelser på bussen och har ingen referens till världen.
   Stationerna når världen bara genom `Station` (`sim/stations/base.py`): `own` och
   `masts_free` (egna instrument), `area_nm`/`patrol_end` (ordern) och `world`, som bara
   finns i stationer med `REACHES_WORLD = True` (sensorer och vapen, med skälet bredvid).
   `tests/test_import_boundaries.py` vaktar det.
   Rapporter får aldrig avslöja sanningens id:n (`DD1`, `T1` …).
4. **`sim/` importerar aldrig Textual.** Gränssnittet bor i `ui/`.
5. **Besättningen föreslår åtgärder** via `Station.suggest(..., order="…")`;
   kaptenen svarar `ja`/`nej`. **Vapenavfyring föreslås aldrig som ja-order.**
   Förslag om sådant kaptenen redan beordrat släpps (`Game.suggestion_redundant`,
   `Order.STANDING`). Ett larmförslag står 30 s mot vanliga förslag (`ALARM_HOLD_S`): ett vanligt
   förslag väntar då i `Game.held` (det nyaste vinner) och kommer när larmet är besvarat, om det inte
   är äldre än 60 s eller någon station säger nej (`vetoes`; `MAST_ORDERS` – sända, periskop, radar,
   foto – föreslås inte när det beordrade djupet är under periskopdjup; vakthavande säger nej till allt
   som tar oss uppåt medan fienden har oss). Vetot prövas också när förslaget levereras, och samma order
   från en annan station inom 30 s släpps (`Game._suggestion_stale`). Ett förslag kommer aldrig före en
   rapport nära det i kön (`ReportQueue`). Gå-ned-förslag tar djupet ur `Station.dive_depth()`. Vid tystnad (10 min) tar vakthavande initiativ ur
   stationernas `idle_proposals()`.
6. Fast tidssteg 1 s. All slump via seedade `random.Random` – inga globala `random.*`. Stationerna
   drar ur sin egen ström `game.rng_for("namn")` (aldrig `game.rng`), så att en ny dragning i en
   station inte flyttar de andra (`tests/test_rng.py`).

## Arkitektur i korthet
- **Sanningslager:** `world.py` (tick-ordning dokumenterad där), `ownship.py`, `ice.py`,
  `enemy.py`, `weapons.py`, `environment.py`, `acoustics.py`, `entities.py`, `pilotage.py`
  (lotsen: andra fartyg girar undan land, efter AI:erna).
  Transienter/emissioner som skapas under ett tick blir hörbara nästa tick.
- **Stationer** (`sim/stations/`): en per system, ärver `Station`. Har `COMMANDS`
  (`CommandSpec`), `on_order`, `update`, `say`, `suggest`. Nya system = ny station
  i `DEFAULT_STATIONS`; `Game` ska inte behöva ändras. Krokar `Game` frågar alla stationer:
  `intercept` (order medan kaptenen går; `confirm_once` frågar en gång om en order som bryter mot
  uppdraget, aldrig om ett förslag kaptenen sagt ja till eller under uppvärmningen), `on_suggestion` (starpom beslutar), `vetoes` (förslag som
  inte får ges), `keeps_time_scale` (ett larm som inte ska sänka tidskomprimeringen), `status_fields`
  (stationens fält i `StatusSnapshot`; `Game.status()` hämtar bara egen ubåt själv och känner ingen enskild station).
- **Navigatören** är paketet `sim/stations/navigation/`: `station.py` (stationen, bestick, order,
  `update`), `common.py` (konstanter och order), `phrases.py`, och delarna som `NavigationStation` ärver:
  `fixes.py`, `bottom.py`, `ice.py`, `steering.py`, `exit_route.py`, `current.py` (strömmen ur fixarna).
  Pågående fixar är uppdrag
  (`tasks.py`, `NavTask` med `abort` och `step`) i `NavigationStation.tasks` per namn ("fix", "starfix",
  "bfix"), körda med `_run_task` på sina platser i `update`; avbrottet skrivs i uppdraget. Styruppdraget
  är ett i taget, `NavigationStation.steer` (`tasks.Steering`: `Follow`, `Attack`, `Wait`, `Fairway`,
  `Station`), med sitt eget tillstånd och `STEP_S`; `nav.goal` är dess namn (follow, attack, wait,
  fairway, station, circle). Ett steg som slutar sätter `steer = None` där det säger varför; `kurs`
  avbryter (`on_order`).
- **Torpedrummet** är paketet `sim/stations/torpedo_room/`: `station.py` (stationen, order, laddning,
  torpederna i vattnet), `common.py` (konstanter, order, `Tube`, `Running`), `phrases.py`, `firing.py`
  (eldledningen, `FiringMixin`) och `wire.py` (trådstyrningen, `WireMixin`). Växer en station sig stor: dela den så (navigatören, radion, torpedrummet).
- **Rapporter** bär `type` + `data`, aldrig färdig text. Texten skapas av
  `phrases.render()` vid leverans, efter rapportfiltren. Varje station registrerar
  sina fraser med `phrases.register({...})` i sin egen modul.
- **Radion** (paketet `stations/radio/`: `station.py`, `common.py`, `phrases.py`, och `reception.py`
  (mottagningen) och `sending.py` (rapporten, pejlrisken) som `RadioStation` ärver): rapporten byggs ur kunskapen i `dispatch.py` (`SentReport`,
  `ReportTransmitted`); huvudstaben (`headquarters.py`) vet bara vad vi sänt och svarar vid nästa
  sambandstillfälle. Båda är kunskap (importtestet). Radion antecknar sanningen bakom varje rapport
  för slutrapporten (`goals.report_summary`).
- **Uppdragsmål** (`sim/goals.py`, sanning): scenariot lägger `Goal`-objekt i `World.goals`
  (`StrikeGoal`, `PhotoGoal`, `ReportGoal`, `SurfaceNearGoal`, `EscapeGoal`, `TrainingGoal`,
  `GroundingFails`, `NoDiveInFjord`, `RecordGoal`); `World._check_outcome` prövar dem i `RANK`-ordning, efter
  sänkt neutralt/alla fiender och före `forced`/`patrol_end`. `World.goal(cls)` hittar ett mål.
  `World.mission` håller bara det som hänt (sänkt, `best_photo`, `last_report_t`, `grounded_t`,
  räknare). Nytt mål = ny klass i `goals.py`, `World` ändras inte.
- **Importgränser** vaktas av `tests/test_import_boundaries.py`: kunskapsmodulerna når aldrig
  sanningen (importer under `TYPE_CHECKING` räknas inte), `sim/` importerar aldrig Textual.
- **Scenarier** bor i paketet `sim/scenario/`: en modul per scenario med sina korta varianter
  (`kuba`, `arktis`, `duell`, `jagad`, `sundet`, `clyde`, `konvoj`, `krig`, `ovning`), det delade i `common` (`Scenario`,
  `Warmup`, platserna, `_crew`, registret). De registreras i `__init__.py` (`register(ScenarioDef(...))`,
  menyns ordning) och väljs i gränssnittets väljare eller med `--scenario`. Scenariot bär områdesnamn
  och sluttexter; `Game` ska inte känna till enskilda scenarier.
- **Krigsskådeplatsen** (`sim/theatre.py`, sanning, krigspatrullen `krig`): en spawner som lägger ut en
  uppgift i taget (`anfall`, `spaning`, `foto`) och skriver stabens telegram när radion tar emot det
  (`Scenario.theatre`, `radiogram.RadioMessage`). Flaggan `tasks` byter `Knowledge.order_tasks` under spelet
  (`TasksOrdered`); utvägen gäller först efter hemkallelsen (`Scenario.escape_task`, `Game.recalled`,
  `EscapeGoal.requires_flag`); `World.open_ended` håller spelet igång när allt är sänkt. Ny uppgiftstyp = ny
  gren i `Theatre` (läggs ut, telegram, avgörande); `Game` ändras inte.
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
  är kaptenens sak), viktiga lösningar ≥ osäker vid överlämnandet. Siffrorna i `kalibrering/README.md`.
- **Order i alla vyer** (`ui/viewbase.py`): vyerna ärver `ViewScreen` (rapportraden, `Esc`, orderrad
  `OrderLine` som visar väntande förslag). Vyns tangenter står i `EMPTY_KEYS` och gäller bara när
  orderraden är tom (Input tar annars alla utskrivbara tecken); bokstäver är aldrig vytangenter.
- **Vyregistret** (`ui/views.py`): varje helskärmsvy är en `ViewDef` (skärmen, orden, namnet i handboken,
  när den står i Tab-ordningen). Registrets ordning är Tab-ordningen; `SubApp` och handboken läser därifrån.
- **Tangenter:** `Tab` växlar vy, `Esc` tillbaka, `ctrl+t` ljud. Undvik F-tangenter
  (medietangenter på Mac) och ctrl-tangenter som orderraden (`Input`) redan använder.
- **Ryska** (`sim/russian.py`): fasta fraser i `WORDS` (translitterering, kyrilliska, svensk
  betydelse). Skriv dem med `ru("Jest")` i fraserna; betydelsen ska framgå av svensk text bredvid,
  aldrig siffror eller bedömningar på ryska. `segments()` delar texten; talet läser ryskan med
  `RU_VOICE` (Milena) och resten med Alva. Ordlistan visas i `hjälp`. Stridslarm (`off.battle_stations`,
  revun) när jakttecken kommer efter 30 min lugn (snabb pingtakt räknas bara med starka pingar,
  ≥ 142 dB mottaget, ~8 nm: `PING_NEAR_RL`; svagare ger `sonar.ping.fast_far` utan larm); avdelningarna rapporterar (`eng.inspected`)
  60 s efter haverilarm eller kraftig tryckvåg.
- **Ryskt tal**: varje station registrerar `RU_PHRASES` med `phrases.register_ru()` ur samma `data`;
  `render()` fyller `Report.speech` (kyrilliskt), annars `russian.fallback()` (vem som rapporterar).
  Hjälp i `russian.py`: `course` (siffra för siffra), `count`/`dec` med rätt böjning, `contact`
  (S-1 → цель 1), `CLASS_RU`. Inget latinskt i talet (testas). `SoundBoard.language` ("ru" som
  standard, `tal ryska`/`tal svenska`); utan Milena svenskt tal. Ny fras ⇒ lägg till rysk fras (testet kräver det för alla utom `phrases.NO_SPEECH`, det som aldrig
  läses upp: systemrader och tabeller). Svensk fritext i `data` (t.ex. `reason`) läses inte på ryska:
  lägg en nyckel bredvid (`why`) eller säg det allmänt ("Выполнить не могу").
  Talsyntesen bor bara i `ui/voices.py` (`backend()`, `MacSay`: röst per språk, `start`, `render`;
  `WebSpeech` i webbläsaren, bara `start`); `say`
  utanför den filen fångas av `tests/test_voices.py`.
- **Webbversionen** (`web/`, GitHub Pages): samma `sim/` och `ui/` i Pyodide med en egen Textual-drivrutin
  (`web/pyodide_driver.py`) och xterm.js. Inga trådar där: det som körs i en tråd behöver en väg utan
  (`ui/app.py`, `THREADS`; `Game.warm_up_steps`; `MenuSound(threaded=False)`). Ljudet: mixern till Web Audio
  (`web/web_audio.py`, `WebOut`, satt som `ui.ambience.OUTPUT`), talet med webbläsarens talsyntes
  (`voices.WebSpeech`), spelaren `audio.WebPlayer`; `ui/` känner aldrig `web/`. Publicerad på
  https://thohig.github.io/silent-service-txt/, bara för hand (`.github/workflows/pages.yml`,
  `workflow_dispatch`): efter ändringar i `sim/`, `ui/` eller `web/` kör `gh workflow run pages.yml`. `web/README.md`.
- **Händelsebussen** (`events.py`) är synkron. `Knowledge` registreras före
  stationerna så att stationer alltid ser uppdaterad kunskap.
- **Utbyggnadskrokar:** rapportfilter (`ReportQueue.filters`, ändrar `data`) för
  trötthet/lojalitet/sabotage; `CrewMember.effective_skill()` för all
  prestationspåverkan; prenumeration på `ReportDelivered` för tal (`say`).

Systemen i detalj (läs filen för det system du ändrar, och uppdatera den där):
- `docs/system/scenarier.md`: Civil trafik, Konvoj, Konvoj i plottet, Anfall, Övningen, Jagarkaptenerna,
  Flyg, Fiendens torpeder (med nedräkningen), Clyde, Krigspatrullen
- `docs/system/hav.md`: Land skymmer, Ljuset, Molnen, Fyrarna, Firth of Clyde, Is, Havsbotten, Strömmen,
  Sjögången, Vädret
- `docs/system/utkik.md`: Bryggan, Periskopet, Periskopbilden
- `docs/system/besattning.md`: Radion och telegrammen, Rapporten till staben, Huvudstaben,
  Slutrapportens samband, Radiospaning, Kärnvapenrådet, Starpom, Trim och flytkraft, Back i maskin,
  Trimmaren, Besättningen under jakt, Fråga en gång
- `docs/system/vyer.md`: Loggen, Sjökortet, Sonarvyn, Huvudraden och sjögången, Ubåten, Djupprofilen, Centralen, Systemtavlan
- `docs/system/granssnitt.md`: Huvudmenyn, Ljud

Avslagna förslag (föreslå inte igen): tal på Linux (piper/espeak-ng), animering på sjökortet, bilder i
terminalen (Kitty/sixel), besättningsfigurer i centralen, reaktorpanel i centralen,
däckskanon, fler vyer (t.ex. plottbord, eldledning, besättningslista, hydrologi: det nya ska synas i
de vyer som finns), vakter och trötthet som system, besättningen som människor (personligheter,
moral; starpom räcker), scenarierna Haveri (K-19), Räddningen, Spaningen och Avhopp, slumpade
kriser, svårighet via besättningens kunskap, ljuskulor, undervattenstelefon i fler scenarier,
primärkrets och strålningsdos, nödutrymning, tjänsteblad (spelade uppdrag sparade mellan körningar), luften som system (syre, regenereringspatroner), huvudbarlast och hydraulik som system, tröghets- och
radionavigering i Arktis. Riktlinje: realismen ligger hos besättningen (rapporter, förslag, fel som
märks), högst en ny order per system, inga nya vyer (se `docs/IDEER.md`).

Idéer som inte är beställda: `docs/IDEER.md`. Konkreta öppna uppgifter (köra om, prova för hand,
utreda, beslut som väntar): `docs/TODO.md`. Stryk det som blir gjort där. Det som gjorts står i
`docs/ANDRINGAR.md` (nyast först: vad det betyder i spel, var det bor, vad kalibreringen visade);
för in varje färdigt steg där.

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
  tappade plottet patrulljagaren och radion gick upp för tidigt); mål som plottet vet sicksackar
  (konvojfartyg eller två märkta girar, `Knowledge.zigzags`) q = 30 (med q = 1 var konvojlösningar
  god/säker med σ 0,02–0,1 nm men 1–3 nm fel, för låg fart); kursens σ ≥ 15/30/60° ⇒ högst
  god/osäker/dålig när målet kan gå (fart + 2σ ≥ 3 kn; med bara farten ≥ 3 kn kallades ett mål
  i 6 kn skattat till 2 kn god med okänd kurs). Brytpunktstestet räknar utan brus. Mot sanningen (ja-boten,
  övning/kuba/konvoj-kort/sundet, 8 frön): grova fel (avstånd > 50 % eller kurs > 90°) bland god/säker
  11 % ⇒ 9 %, fel > 3σ 18 % ⇒ 11 %; säkra lösningar med kurs > 90° fel 6 % ⇒ ~1 %. Efter slumpen per
  station och q för sicksack (2026-11-18): grova 6,9 % ⇒ 4,8 %, > 3σ 10,4 % ⇒ 7,9 % (konvoj-kort god
  grova 18 % ⇒ 8 %). Avståndets σ har ett golv på 0,05 nm (`RANGE_SIGMA_FLOOR_NM`, ~båtens längd): utan det
  kollapsade lösningar på patrullbåten i sundet mot oss med σ ≈ 0 och kallades säkra (sundet säker grova
  18 % ⇒ 0); alla scenarier grova 4,8 % ⇒ 3,9 %, > 3σ 7,9 % ⇒ 6,0 %. Kurstaket när målet kan gå (2026-11-21, övning/kuba/konvoj-kort/sundet/krig-kort): god grova
  6,5 % ⇒ 5,3 %, säker grova 2,5 % ⇒ 1,7 %, säker > 3σ 9,5 % ⇒ 5,1 %. Det som är kvar är mest girar de senaste minuterna som plottet inte hunnit se. Mätskriptet: `kalibrering/tma_kvalitet.py`.
- Radion: rapporten 6 s + 4 s per femsiffergrupp (kort ~22 s); fiendens pejlnät pejlar aldrig under
  10 s, alltid över 25 s, σ = 1,5 nm · √(30 s / längd), 0,7–3 nm (`DF_*` i `enemy.py`).
- Back i maskin: broms 0,15 kn/s mot farten, backfart 8 kn (turbin) / 3 kn (smygmotor), gir ⅓ och
  djuproder 30 % akterut, omkastning 120 + 2,5·fart dB från ≥ 2 kn, kavitation akterut vid halva farten.
- Sjögången (Beaufort, `docs/system/hav.md`): havsbrus +2,5 dB per steg från 3, jagarens ping −3 dB per
  steg från 5, mastradar ×0,5 vid 4 och ×0,25 vid 6, sikt ×0,6 vid 6; sjön suger från 4 (2,4 m per meter
  våghöjd i ≤ 2 kn), tornet bryter ytan med kölen grundare än 13 m. Kuba 3, konvoj 5, övning/sundet 2.
- Provdjup 300 m, krossdjup 450 m, periskopdjup ≤ 18 m, antenndjup ≤ 30 m, torpedavfyring ≤ 100 m och ≤ 12 kn.
  Långvåg med flytkabeln ≤ 50 m och ≤ 5 kn, 5 min; hel med två av mörker, ≤ 3 kn och ≤ 40 m.
- Clyde: Polarisbåten 130 + 2·fart dB i ytläge; bandet 10 min med SE ≥ 8 dB (`stations/recording.py`);
  fyrfix σ 0,1 (två) / 0,2 (en); moln ≥ 0,6 stänger stjärnfixen. Firth-bottnen i ett rutnät 0,05 nm.
- Omladdning: två slammer à 145 dB (torpeden in, bakluckan stängs); på smygmotorn eller jagade laddar
  minören försiktigt, 8 min i stället för 5 och −12 dB. Jagaren hör slammret ~1,5 nm över skiktet i 5 kn.
- Jakten (`docs/system/besattning.md`): maskins sprint 220 m, godtar beordrat 180–290 m; smygmotor tidigast
  10 min efter senaste jakttecknet; sonars undanmanöver uppåt bara till skiktet + 60 m; undervattenstelefonen
  och "mycket starka" 2, 4, 8 … högst 30 min emellan; skenmål högst var 20:e min; nära pingare (≥ 142 dB)
  1,5°/s, högst 60°; ingen botten när skarpa laddningar fallit nära de senaste 5 min. Radarvarnaren
  upprepar en fartygsradar efter 30 min (eller ny styrka, > 15° i bäring). Ytläge sedda: 60 s att dyka.
- Tystnad i båten: jagade och på smygmotorn eller ≤ 6 kn (`OfficerStation._hush_watch`, hävs efter 60 s).
  Skrovknak 132 dB var 25:e m vid djupändring > 1 m/s under 80 m (rodren i ≳ 6 kn); maskin säger det under jakt.
- Trådstyrd 53-62T (försök): 35 kn, 7 nm, tråd 5,5 nm; styrs var 20:e s, målsökaren släpps 0,6 nm från
  målet; tråden av efter 15 s över 12 kn, gir > 90° från kursen vid skottet, ~1 %/min av sig själv.
- Fiendens torped Mk 37: 26 kn, 5 nm, 145 dB, söker passivt i 40° och aktivt inom 0,4 nm och ±50 m i höjd;
  skenmålet 135 dB och bubbelekot starkare än skrovet; en träff är förlusten. Vi går 28 kn på turbinen.
- Trim (`sim/trim.py`): kompression 1 t/100 m, skiktet bär 3 t, smältvatten 1 t, torped netto 0,6 t förut,
  rodren 0,8·v² t (högst 10), drift 0,03 m/s per ton, styrningen borta vid 2 t, pumpar 1 t/min och 121 dB.
  Ny djuporder i ≤ 2 kn och uppstigning till ytan görs med barlasten (trimmen spelar ingen roll).
- Scenariernas och systemens siffror (botar, frön, utfall) står i `kalibrering/README.md` under
  Siffrorna. `uv run python kalibrering/kontroll.py` jämför passiva boten och ja-boten med
  `kalibrering/baslinje.json`; `kalibrering/fingeravtryck.py` visar att en omstrukturering inte
  ändrar spelet (samma frö ⇒ samma rapporter).

## Arbetssätt
- Bygg i steg och **committa efter varje steg** (användaren vill det). Vid större
  nya delar: föreslå struktur och invänta ok.
- Nytt system ⇒ tester i `tests/`. Statistiska påståenden (TMA, sonar) testas över
  flera seeds, inte ett enda lyckat frö.
- Testerna körs parallellt (pytest-xdist, `-n auto` i pyproject; `-n0` för seriellt). Ett test som
  tar mer än ~1 s (hela spel, flera frön, uppvärmning, gränssnitt) märks `@pytest.mark.slow` och körs
  bara med `--slow` (`tests/conftest.py`). Kör `uv run pytest -q` lokalt före varje commit, och `--slow`
  före större steg (nya system, kalibrering). GitHub Actions (`.github/workflows/tester.yml`) kör bara de
  snabba testerna vid push till main och `--slow` vid pull request eller manuellt (`workflow_dispatch`);
  ändringar som bara rör `.md` och `docs/` kör inget. Eftersom vi committar direkt på main har CI hittills
  aldrig kört `--slow` (alla körningar vid push, 2026-11-21): de långsamma körs bara lokalt. Repot är offentligt sedan 2026-11-21 (minuterna är
  gratis). `setup-uv` har inga flyttande huvudtaggar: exakt version (`@v10.3.3`); övriga actions på huvudversion. Scenariotestet hoppar över de korta
  varianternas uppvärmning utan `--slow`.
- Verifiera spelkänslan med en huvudlös genomspelning: skapa `Game`, prenumerera
  på `ReportDelivered`, skriv ut rapporter, kör `g.tick()` i en loop (gärna med
  en bot som svarar `ja` på förslag). Tillfälliga skript i scratchpad; botar som ger siffrorna ligger i
  `kalibrering/` (siffrorna i dess README) och uppdateras där.
- Gränssnittet kan provköras med `App.run_test()` och `save_screenshot()`.
- Sanningsloggen (`logs/truth-*.log`) visar exakta positioner, fiendens tillstånd
  och datum – använd den för felsökning.

## Fallgropar
- `Game.chart()`, `profile()`, `sonar()` och `systems()` byggs en gång per läge (tick, order,
  tidsskala, händelse på bussen) och är bara till läsning. Ändrar ett test en stations tillstånd
  direkt: `g.invalidate_views()` före nästa vy.
- Döp aldrig en metod i en Textual-widget till `_render` (krockar med Textual).
- En vy som har egen `on_mount` ska inte anropa `super().on_mount()`: Textual kör redan
  `ViewScreen.on_mount` (går genom MRO), och då startar timers två gånger.
- `ReportLog` tar aldrig fokus och kommandopaletten är av (`ENABLE_COMMAND_PALETTE`): orderraden ska
  alltid ha fokus. Ny widget som kan ta fokus i en vy: `can_focus = False`.
- Ett tyst uppdrag (navigatörens egen pejling) avbryts tyst: `NavTask.abort` ger en tom typ.
- Timer-callbacks i `ui/app.py` kan köras under nedstängning – skydda mot `NoMatches`.
- Förslag spärras per nyckel med `cooldown`; glöm inte det, annars spammar
  besättningen.
- TMA antar rak kurs; om målet manövrerar ska plottlaget säga det och börja om
  (`ContactTrack.tma_from_t`), inte rapportera en orimlig lösning.
