# Scenariernas system

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

- **Civil trafik:** `traffic.py` (sanning). `World.spawners` skickar in nya fartyg,
  `MerchantAI` styr dem. Neutrala fartyg (`World.neutral_ships`) är inte fiender; sänks
  ett slutar spelet (`neutral_sunk`). Kunskap: `ContactTrack.civil`/`warship`; civila
  räknas inte som hot men plottas tyst för kortet. Torpedrummet (`torp.neutral`) varnar före ett skott
  med rak torped och i `skjutlösning` när ett känt handelsfartyg ligger inom 0,5 nm från en bana hela
  vägen ut (plottets lösning ≥ osäker), eller utan lösning med bäringen inom 10°; upprepad order inom
  en minut skjuter (varning, inte vägran). Med målsökande torped gäller i stället andra kända fartyg inom
  0,6 nm från målet när torpeden är framme (`_seeker_rivals`): målsökaren tar det den hör bäst. `skjutlösning` utan kontakt tar den enda hållna kontakten, annars hotkontakten
  med bäst lösning (närmast vid lika, `_best_target`). Torpedrummet säger ingen ny skjutlösning (`torp.ready`)
  på ett mål som våra torpeder är på väg mot.
- **Konvoj:** `convoy.py` (sanning). `Convoy` är en spawner med en ledpunkt som sicksackar efter
  `ZIGZAG_PLANS` (medelavdrift ~0) kring baskursen; `ConvoyShipAI` håller platsen (fast i baskursens
  riktning). Nödgir 50° bort från hotet, +3 kn i 15 min (sänkt fartyg, egen torped < 1,5 nm,
  detonation < 4 nm), sedan baskurs och plan igen. Typer `transport` (145 + fart dB) och `tanker` (143).
  Eskort (`EscortAI(DestroyerAI)`, `make_escorts`): skärm 2,5 nm framför och 1,5 nm åt sidorna, fast
  i baskursens riktning; ping var 20:e s; skarpa från start (`roe="lethal"`); koppel 4 nm från
  ledpunkten; en jagar i taget (`Convoy.hunter`), den andra bara om datumet ligger < 1,5 nm från
  konvojen. Konvojens brus skymmer ubåten (`masking_noise(sides=...)`). Ubåt 1 nm från konvojens väg,
  3 kn: hittas i 8 av 8 frön på 50 och 150 m, ~25 min efter start (2–4 nm), ett anfall, sedan går
  konvojen vidare och eskorten släpper. (Siffran är från Beaufort 4; sedan 2026-11-19 går konvojen i 5,
  4–6 med vädret: eskorternas ping −3 dB, deras radar och utkik mot masterna ×0,35, havsbruset +5 dB, och
  periskopdjupet kräver ~6 kn; se `docs/system/hav.md` och `kalibrering/README.md`.)
  Motanfallet (`konvoj-mot`, `_CounterattackWatch`): vaktens salva frågar torpedrummet en gång om målet;
  varnar torpedrummet i stället för ett neutralt fartyg i banan (`_neutral_warned`) byter vakten mål
  (`skip`) i stället för att upprepa (förut neutral sänkt i 2 av 24 frön, 3 och 9 min efter överlämnandet).
- **Konvoj i plottet** (`zigzag.py`, kunskap): vid varje målmanöver sparar plottet benets sista
  lösning ≥ osäker (`ContactTrack.legs`, `turns`). Baskurs = viktad rak linje genom benlägena
  (σ läge + 0,8 nm sicksack), farten = median av benens fart längs baskursen; kvalitet ur σ och
  tak efter antal ben (2 ben ⇒ högst osäker, 3 ⇒ god). Benlängd = median av gap per kontakt.
  Gruppering: ≥ 2 icke-jagare inom 3 nm, ±30°, ±4 kn; jagare inom 5 nm är eskort. `ConvoyAssessed`
  ⇒ `Knowledge.convoy`. Konvojens girar sägs som `plot.convoy.turn`, inte `plot.maneuver`.
  Konvojfartyg och mål med två märkta girar (`Knowledge.zigzags`) räknas med processbrus q = 30
  (`tma.ZIGZAG_MANEUVER_Q`) i stället för 1: annars blev lösningen god/säker med för litet σ och 1–3 nm
  fel när målet girat inom fönstret.
  Med periskoptitt var 4:e min: baskurs inom 5° och säker efter ~10 ben; bara sonar: grov fart
  (TMA drar avståndet mot 6 nm), kvaliteten dålig/osäker.
- **Anfall** (`anfall S-x`, navigatören, `firecontrol.approach`): kurs till en punkt 1,2 nm vid sidan
  av målets väg (konvojens baskurs om ≥ osäker, annars nuvarande ben eller TMA-lösningen) där målet
  är tvärs 4 min efter att vi är framme; omräkning var 30:e s. Hinns det inte i vår fart föreslås
  lägsta fart som räcker (inom 1,5 h). I skjutläge (tvärs inom 8 min, ≤ 2,5 nm från vägen) föreslås
  fart 3. Passerat (bakom, två gånger i rad, säkert bara med baskurs eller < 3 nm) ⇒ slutar.
  Torpedrummet (`_leg_warning`) varnar när gångtiden är längre än det som är kvar av benet. Samma varning
  gäller varje mål med två märkta girar (benet ur girarna, `_turn_rhythm`) och en jagare som jagar oss
  (`Knowledge.hunting`: girar hela tiden, varning vid gångtid över 2 min, `HUNTING_RUN_S`); med en rak torped
  säger den att en målsökande har större chans.
  Fyra provkörningar (periskop var 4:e min): framme i alla, närmaste passage 0,2–3,3 nm.
  Besättningen visar vägen (aldrig avfyring): navigatören (`_convoy_watch`, var 30:e s) föreslår
  `anfall S-x` när plottet har konvojen, eller ett ensamt stort fartyg med färsk lösning ≥ osäker, och
  vi ligger framför (inte jagade, inte inom 20 min efter skjutläge, var 5:e min). Vakthavande föreslår
  `periskopdjup` och sedan `periskop S-x` var 4:e min när konvojen är känd eller sonar hör stora fartyg
  (`is_big_ship`: klassning stort/transport/tank, inte civilt), utom när vi är jagade, en klassad jagare
  är < 3 nm enligt plottet eller radarn varit mycket stark senaste 5 min. Titt före skottet
  (`_fire_look`, 2026-11-18): ett stort fartyg ≤ 3,5 nm enligt plottet (lösning ≥ osäker) ⇒
  `off.suggest.fire_look`, `periskop S-x` när förra titten på det är ≥ 90 s gammal (i stället för de
  vanliga konvojtittarna); en jagare < 3 nm stoppar inte förslaget utan nämns ("masten kan synas"). 8 frön, ja-boten: framme i
  4 (förut ~2); ja-boten som skjuter `salva` när navigatören säger skjutläge sänker 1–2 (förut 0).
- **Övningen** (`ovning`, `training_scenario`): 8 okt 1962, 10:00, ytläge med bryggan bemannad i
  Kolafjorden utanför Poljarnyj, kurs ut, 10 kn. Botten `kola_seabed` (`seabed.Fjord`: land söder om
  kusten utom längs en fjord efter `path` med `half_w`/`depth` per punkt, holmar nära stranden minst
  `ISLAND_CLEAR_NM` från mitten, `in_fjord`); mynningen ~7,7 nm norrut, 260–340 m utanför. Farleden
  (`Scenario.fairway` ur sjökortets fjord ⇒ `Knowledge.fairway`/`fairway_to`, ritas `╌`). Navigatören
  (`farleden`, goal "fairway") styr 0,15 nm till styrbord, gir 0,25 nm före brytpunkten, säger
  `nav.fairway.done` (fritt att dyka) och föreslår `kurs mot övningsområdet`; föreslår `farleden` i
  fjorden (var 10:e min). Landvarningen tiger om landet ligger bortom girpunkten. En dykorder i fjorden
  frågar navigatören om en gång (`confirm_once`); upprepad inom en minut dyker vi och övningen är förlorad. Fix från bryggan
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
  undervattenstelefonen (`exercise.torpedo_report`): träff = under kölen (genom skrovets ellips, `weapons.hull_pass`), annars
  avstånd i meter. 8 frön, bot som skjuter en torped när lösningen är god: klar på 99–121 min,
  träff i 4, bom på 140 m i 1, långt bom (830 m, eller torpeden hördes aldrig) i 2, ingen avfyring i 1
  (omkört 2026-11-15; förut träff i 2, bom 70–90 m i 4).
  Kort variant (`ovning-kort`, 40 min): start på periskopdjup 4 kn inom 0,4 nm från
  övningsområdet, vakt 4 min (periskopsvep, fix), stegen från `djup100`, tidsgräns 60 min.
  8 frön: första förslag efter ~67 s; ja-boten klar på 41–53 min i 7, tiden ute i 1 (torpeden hoppas
  över); bot som skjuter klar på 22–52 min, träff i 3 (omkört 2026-11-15; förut 35–51, 25–37 och
  träff i 1); passiv kapten: tiden ute.
- **Jagarkaptenerna** (`enemy.py`, `Temperament`, J1–J2): varje `DestroyerAI` (och eskort) har ett
  temperament ur en egen ström (`draw_temperament`, drar inte ur jagarens): metodisk (som förut), envis
  (söker i 10 kn, girar var 90:e s, håller ett gammalt datum 30 min i stället för 15) eller ivrig (stänger i
  27 kn, söker i 16, pingar var 0,8:e gång, går in redan när datumet är 0,5 nm, ger upp efter 10 min).
  Hamnens patrullbåtar är alla metodiska (`DRAW_TEMPERAMENT`). Spelaren märker det genom plottet
  (`PlotTeam._hunter_watch`, kunskap): efter 10 min jakt säger plottet jagarens fart (lösning ≥ osäker, färsk)
  och pingtakt (mediangapet mellan hans pingar de senaste 5 min: tätt ≤ 10 s, glest ≥ 20 s), och efter 25 min
  att han inte ger upp. Under jakt är lösningen oftast för dålig för farten; pingtakten finns nästan alltid.
  I ytläge: sedd av en jagare (medveten eller < 6 nm) har vi en minut att dyka innan uppdraget slutar
  (`SURFACE_GRACE_S`); navigatören frågar före ytläge med en fiende i plottet (`docs/system/besattning.md`).
- **Flyg:** `air.py` (sanning). `AirPatrol` (en spawner) skickar ett plan i taget;
  `AircraftAI` söker med radar, bojar och MAD och ger jagaren datum (`DestroyerAI._set_datum`).
  Plan och bojar är `Vessel` som inte är fartyg (`is_ship` falskt, tysta). Besättningen
  märker flyget via radarvarnaren, periskopet och transienterna `buoy`/`buoy_ping`.
  Radarvarnaren (vakthavande, var 10:e s på periskopdjup) publicerar `AirRadarHeard` med starkaste
  flygradarn eller None ⇒ `Knowledge.air_radar`, `air_close_t` (stark/mycket stark, `AIR_CLOSE`).
  Vakthavande föreslår `djup 60` så länge flygradarn är nära (larm, spärr 2 min). Radion föreslår inte
  `sänd rapport` medan senaste svepet hörde flyget nära, och inte periskopdjup inom `AIR_QUIET_S` (2 min)
  efter; drev flyget ned oss under fönstret föreslår den periskopdjup igen efter 2 min
  (`radio.suggest.air_clear`), om minst `AIR_LEFT_S` (2½ min) av fönstret är kvar.
  Sjöklotter (`environment.radar_clutter_f`): radarns räckvidd mot masterna ×0,5 vid Beaufort 4, ×0,25 vid 6;
  mot ett torn som brutit ytan (`OwnShip.broached`) som mot en ubåt i ytläge.
- **Fiendens torpeder** (`weapons.py`, D1): `launch_enemy_torpedo` skjuter en Mk 37 (`MK37`: 26 kn, 5 nm,
  145 dB) med side "enemy". Den söker mot oss och våra skenmål (`_seek_enemy`): passivt mot det som låter
  mest i konen (40°), aktivt inom 0,4 nm och ±50 m i höjd (`ACTIVE_DEPTH_M`), där skrovet ekar 15 dB och
  skenmålets bubbelmoln 18 dB. Låsningen hålls (+6 dB, `RELOCK_DB`), ett passerat skenmål bortses från.
  Träff bara på rätt djup (±20 m) och då är vi förlorade (`TORPEDO_HIT_HULL`). `lead_course` siktar med
  förhållning. Sonar (`sonar.py` `IncomingTorpedo`, `stations/incoming.py`) hör den genast, ropar Torped
  i vattnet (larm, stridslarm i ljudet) och föreslår undanmanöver i en order: svag signal (långt bort)
  skenmål, kurs bort, turbin, högsta fart och nytt djup; stark (`CLOSE_SE` 8 dB, ~2,5–3 nm under isen)
  skenmål, smygmotor, tvärs och nytt djup. Djupet räknas från där vi var när torpeden hördes (där den
  söker), 80 m därifrån, och gäller tills nästa torped. Sedan bäringen och dess drift var 20:e s (står
  den still kommer den mot oss, förslaget upprepas om inget väntar). Den torped som hörs starkast styr.
  Nedräkning (T1, `eta_estimate`): när bäringen står still räknar sonar tiden tills torpeden är framme ur
  hur fort den mottagna nivån stiger (`IncomingTorpedo.level`, avläst med σ 0,7 dB): τ = 8,7 dB / (dB/s),
  minsta kvadrat över 40 s, oberoende av farten vid sfärisk spridning. Kvaliteten ur lutningens σ med ett
  modellfel på 20 % (`ETA_MODEL_REL`; torpeden går inte rakt mot oss), 10/25/50 %; över 2 min högst
  osäker, över 4 min sägs ingen tid. Under 90 s ropas den var 10:e s. Mot sanningen (kuba/arktis, 8 frön,
  4 lägen): god inom 30 % eller 10 s i 83–92 %, osäker i 59–79 %.
  `Knowledge.torpedo_alarm` och `doors_t` håller maskinens sprint- och kavitationsförslag borta.
- **US-ubåten i krig** (`arctic.py`, `SubmarineAI.roe = "attack"`, D2): håller 2,5 nm (`ATTACK_NM`) i 8 kn,
  medlar pejlingarna senaste minuten (σ/√n), räknar vår kurs och fart ur dem, öppnar torpedrören
  (transient `doors`, 150 dB; sonar larmar och föreslår kurs tvärs och nytt djup) och skjuter 30 s senare
  med förhållning, högst var 8:e min, 3 torpeder. Tappar den oss söker den där vi hördes sist i 6 kn
  (`_search`); den har oss bara med en pejling ≤ 5 min gammal (`AWARE_S`), annars kommer vi undan.
- **Duellen under isen** (`duell`, `duell-kort`, `scenario/duell.py`, D3): krig 28 okt 1962, Nord-3. En
  amerikansk Skate-ubåt (bas 129 dB, högst 18 kn) skyddar isön T-3 och har order att sänka oss. Sänk den
  (`sank`) eller lämna området utan att den har oss (`escaped`, marginal 1 nm); 4 h. Kort variant: den har
  pejlat oss och är 3–4 nm bort, vakten 3 min på smygmotor, vi nära södra kanten, 40 min. För att skjuta
  måste vi upp till ≤ 100 m. En rak torped går på 5 m och träffar bara inom 20 m i djup, så mot ubåten på
  djupet duger bara målsökarna (SET-53, 53-62T), som styr i djup mot den. Siffrorna i `kalibrering/README.md` (`kalibrering/duell.py`).

- **Clyde** (`clyde`, `clyde-in`, `scenario/clyde.py`, `sim/clyde.py`, N2–N6): 20 okt 1962, brittisk
  sommartid. Lång: 21:30 öster om Pladda på 60 m; Polarisbåten (`TransitAI`, kind `ssbn`, 130 + 2·fart dB i
  ytläge, alltså ~150 dB i 10 kn) lämnar depåfartyget i Holy Loch 00:30 ± 30 min, går 5 kn förbi Dunoon och
  sedan 10 kn ned genom västra rännan (`POLARIS_ROUTE`) och ut förbi Pladda. Inspelningen (`RecordGoal`,
  sonarrummets bandspelare `stations/recording.py`): 10 min med SE ≥ 8 dB över tröskeln ur sonarens egna
  bäringar (över skiktet ≲ 1,8 nm, under skiktet hälften), bara när ordern kräver `inspelning`. Sonar säger
  när bandet går, halvvägs, när ljudet blir för svagt och när det är klart, och föreslår djup 40 (över
  skiktet) eller kurs mot kontakten i 5 kn; navigatören föreslår inte att lägga sig på botten och sonar inte
  att gå under skiktet medan vi ska lyssna och inte är jagade. Klar inspelning ⇒ `RecordingMade` ⇒
  `Knowledge.recorded` (vägen ut är det som återstår) och `mission["recorded"]`. Sedan ut söder om y = 2
  (`EscapeGoal(requires_record="SSBN")`) före 07:30; Polarisbåten söder om y = −3 utan band ⇒
  `record_missed`; grundstötning ⇒ `grounded`. Bevakningen: hydrofonlinje tvärs västra rännan norr om
  Little Cumbrae (y = 19,3) och två patrullbåtar (metodiska), en där och en vid Toward–Dunoon;
  Largs-rännan obevakad. Ingen minering (fred). Tre fiskebåtar (`FishingAI`, 128 + 1,5·fart dB) trålar
  mellan Arran och Ayrshire; handelsfartyg till och från Greenock och färjan Wemyss Bay–Rothesay till 21:45
  (`ClydeTraffic`). Tidvattnet sätter 355° (floden), 1,0–1,4 kn vid 60 m, starkare i grunda sund (upp till
  ×1,5). Kort (`clyde-in`): 01:20, vakten 8 min på smygmotor norrut på 50 m (över skiktet), 1,9–2,6 nm
  vid sidan av Polarisbåtens väg söder om Little Cumbrae, besticket σ 1,0 nm (`Scenario.start_fix_sigma`, felet
  dras ur en egen ström), Polarisbåten 3–4 nm norr om oss, tidvattnet vänder 5–15 min efter
  överlämnandet; målet är bara bandet (`recorded`), 40 min.
- **Krigspatrullen** (`krig`, `krig-kort`, `scenario/krig.py`, `sim/theatre.py`, 2026-11-20): krig 28 okt
  1962, 06:30, kvadrat 14 (30 nm) norr om Kuba, Beaufort 4 (3–5), handelstrafik öster–väster och flyg. Ingen
  fast plan: **krigsskådeplatsen** (`Theatre`, sanning, en spawner först i `World.spawners`) lägger ut en
  uppgift i taget och skriver stabens telegram om den. Uppgifterna: `anfall` (konvoj med 3 transporter och
  en tanker, 10–12 kn, 2 eskorter), `spaning` (landstigningsstyrka, 2 transporter i 13–15 kn och 2 eskorter:
  rapportera kurs och fart, `report_requested`) och `foto` (3 fartyg till ankars, `moored`, och en vaktjagare
  som lyssnar i patrull i en ruta ±2,5 nm, skarpa regler). Den första, en konvoj 16–22 nm bort, står i ordern
  (`known_positions` med kurs och fart och flaggan uppgift); sedan `foto`, `spaning`, `anfall` i tur
  (`TheatreDef.kinds`), 12–16 nm bort (ankarplatsen 6–9 nm). Nästa uppgift läggs ut 5 min före nästa
  sambandstillfälle (07.30, sedan var 90:e min). Telegrammet skrivs när radion tar emot det (`deliver`):
  läget med stabens fel (σ 2 / 2,5 / 0,8 nm), kurs avrundad till 10°, fart i hela knop; missar vi
  tillfället sänds det igen med nytt läge. Det bär `tasks` ⇒ `TasksOrdered` ⇒ `Knowledge.order_tasks` (och
  `order_tasks_t`, `task_place`), och positionen med `motion` ⇒ `Waypoint.at(t)` räknar fram läget (σ växer
  2 kn). Navigatören föreslår `kurs mot <plats>` när uppgiften kommer och igen var 15:e min om vi gått mer
  än 30° ifrån den (tills vi är 3 nm från platsen eller plottet har ett hot); till en fast plats > 6 nm bort
  med marschfart (`turbin, fart 8`). Radion föreslår rapporten under en spaningsuppgift när plottet har en
  lösning ≥ osäker på en kontakt som kommit efter uppgiften (inte jagade, inget hot inom 5 nm).
  Vakthavande föreslår periskopdjup och svep inom 3,5 nm (+ σ) från ankarplatsen; fotot föreslås efter
  svepet som förut. **Avgörandet** (sanning, var 10:e s): `sänkt` (minst ett mål sänkt och 10 min sedan
  utan jägare, eller allt sänkt), `rapporterad` (en rapport efter telegrammet med något av styrkans fartyg,
  eskorten räknas: `mission["report_truth"]` har sanningens id), `fotograferad` (ett foto ≥ osäker efter
  telegrammet, `mission["photos"]`), `missad` (förbi oss och > 10 nm bort, eller 5 h / foto 6 h),
  `inställd` (hemkallelsen kom). `mission["war_tasks"]` och `war_sunk` (tonnage: transport 12 000,
  tanker 16 000, jagare 2 400 ton) ⇒ slutrapporten (`task_summary`, `ui/widgets.war_rows`). Avgjorda
  uppgifter > 15 nm bort tas bort ur världen. **Hemkallelsen** efter 3 uppgifter, ≤ 4 konventionella
  torpeder kvar (16 från start), skrovet < 50 % eller kl 16.30: ÅTERVÄND (`tasks` = ut, `recalled`); då
  gäller `EscapeGoal(requires_flag="recalled")` (2 nm utanför kanten, ingen jägare) ⇒ `patrol_done`, och
  `Scenario.escape_task = "ut"` gör att `Game.escape_nm` och navigatörens väg ut gäller först nu (med
  marschfart om vägen är > 6 nm och inget hot), och att plottet inte föreslår TMA-ben (`Game.recalled`).
  Tiden är ute 20.30 (`patrol_end`). `World.open_ended`: alla fiender sänkta avslutar inte. **Följderna**
  (`TheatreDef.hunt`): pejlar nätet en sändning (samma regel som jagarna, `enemy.df_probability`/`df_sigma`,
  `mission["war_df"]`) går flyget dit 15–30 min senare (`Theatre.air_cue`, flygets datum) och, högst en
  gång i timmen, en jaktgrupp med två jagare (skarpa, `start_hunt` mot fixet, söker i en ruta ±5 nm med
  koppel 4 nm, går hem efter 3 h); en sänkning drar flyget till platsen. Kort (`krig-kort`): kvadraten
  20 nm, vi 3–4 nm innanför nordkanten på kurs 090/270, konvojen 11–13 nm norrifrån (kurs 180–230; den går
  10–12 kn, så 5–9 nm vid överlämnandet som i konvoj-kort), vakten 35 min som i konvoj-kort, bara den
  uppgiften (missad redan 6 nm förbi), sambandstillfälle var 30:e min från 07.35, hemkallelsen senast
  08.05, tiden ute 09.25. En ny uppgift utan rapport häver stabens väntan på en (`Headquarters.
  cancel_report_request`: påminnelserna i kö stryks). Hemkallade föreslår navigatören inte botten (om vi
  inte är jagade) och föreslår fart 4 ut om vi ligger still med hot i plottet. Siffrorna i `kalibrering/README.md` (`kalibrering/krig.py`).
- **Kärnvapenordern per scenario** (`Scenario.nuclear_order`, `at_war`; 2026-11-19): kuba, jagad, sundet och
  arktis "bara på order från Moskva" (rådet kan häva det vid skarpt angrepp, se Kärnvapenrådet i
  `docs/system/besattning.md`); jagads andra telegram villkorat (skarpa sjunkbomber); konvojen och duellen
  förbjudet och krig; övningen förbjudet. T-5 finns i reserven (2) utom i övningen och måste laddas i en tub.
