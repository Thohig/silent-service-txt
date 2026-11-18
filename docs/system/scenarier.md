# Scenariernas system

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

- **Civil trafik:** `traffic.py` (sanning). `World.spawners` skickar in nya fartyg,
  `MerchantAI` styr dem. Neutrala fartyg (`World.neutral_ships`) är inte fiender; sänks
  ett slutar spelet (`neutral_sunk`). Kunskap: `ContactTrack.civil`/`warship`; civila
  räknas inte som hot men plottas tyst för kortet. Torpedrummet (`torp.neutral`) varnar före ett skott
  med rak torped och i `skjutlösning` när ett känt handelsfartyg ligger inom 0,5 nm från en bana hela
  vägen ut (plottets lösning ≥ osäker), eller utan lösning med bäringen inom 10°; upprepad order inom
  en minut skjuter (varning, inte vägran).
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
  Torpedrummet (`_leg_warning`) varnar när gångtiden är längre än det som är kvar av benet.
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
- **Flyg:** `air.py` (sanning). `AirPatrol` (en spawner) skickar ett plan i taget;
  `AircraftAI` söker med radar, bojar och MAD och ger jagaren datum (`DestroyerAI._set_datum`).
  Plan och bojar är `Vessel` som inte är fartyg (`is_ship` falskt, tysta). Besättningen
  märker flyget via radarvarnaren, periskopet och transienterna `buoy`/`buoy_ping`.
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
  måste vi upp till ≤ 100 m. Siffrorna i `kalibrering/README.md` (`kalibrering/duell.py`).

