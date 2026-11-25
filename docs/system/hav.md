# Havet, isen, botten och ljuset

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

- **Land skymmer** (`World.land_between`, prov var 0,05 nm): ljud genom land +60 dB (`land_loss` i
  `tl_to_own`, jagarens och US-ubåtens `_tl`), bryggan och periskopet ser inte fartyg bakom land.
  Djupgående i ytläge 7 m (`SURFACE_DRAFT_M`): ytläge kan gå på grund. Med bryggan bemannad föreslår
  vakthavande inget periskopsvep och sonar ingen fart 4; i ytläge föreslår maskin inget om kavitation.
- **Ljuset** (`sim/sky.py`, `Environment.light(t)` ⇒ `Light`): solens och månens höjd och azimut ur
  scenariots plats (`_place`: lat/lon, lokal medeltid, Kola UTC+3) och orderns datum (`Game` sätter
  `env.date` ur `DATUM:`). Faser dag (sol > −0,833°), skymning (borgerlig, till −6°), nautisk (till −12°),
  natt; `morning` = gryning. `level` 1 → 0,5 → 0,1, natt 0,05 + 0,3·månljus; sikt 10 → 6,25 → 2,5 nm,
  natt × (1 + månljus). `daylight` (nivå ≥ 0,5) för foto, plask, flyg, landmärken, hamnnät. `silhouette(b)`:
  dag/borgerlig överallt, nautisk inom 75° från solen, natt i månglittret (±35°, månljus ≥ 0,2); annars bara
  lanternor. Siluett utan dag: kursens σ × 1,6 (högst mastoppar). Utan plats följer ljuset sunrise/sunset
  (testerna sätter `env.lat = None`). Okt 1962: fullmåne 13, nymåne 28. Soluppgång kvadrat 7 ~06:05
  (förut 06:10). Botarna (sundet, sundet-in, konvoj-kort salva, kuba-kort, arktis-kort) gav samma utfall
  före och efter.
  Månglittret (`DestroyerAI.glitter_factor`, även patrullbåten): på natten med månljus ≥ 0,2 och oss inom
  ±35° från månens bäring sett från fartyget ser utkiken masterna × 1,5 lättare. Krisens nätter (22–28 okt)
  har för lite måne för det, så kalibreringen ändras inte.
  Himlen i bilden (`PeriscopePicture.phase`/`morning`/`sun`/`moon` via `periscope.sky_of`): `draw_sky` i
  `ui/periscope_render.py` (bryggan och okularet) ritar skymningens sken i strimmor åt solens håll (inom 80°),
  solens och månens skiva i braille (månen med fasen, tilltagande ljus till höger; för högt ⇒ utanför bilden)
  och glittret på vattnet under dem; stjärnor bara i nautisk skymning (glest) och natt. Rubriken `phase_text`:
  dag, gryning/skymning, nautisk …, natt med månen.
  Almanackan (`Knowledge.almanac`, `environment.Almanac`: plats, datum, klocka; samma astronomi, ingen världen).
  Vakthavande (`stations/daylight.py`, `LightWatch`, var 30:e s): `light.sunset_soon`/`sunrise_soon` (30 min),
  `light.sunset`, `light.dark` (med månen), `light.dawn`, `light.sunrise`, `light.moonrise` (≥ 30 %); i ytläge med
  hot i plottet och solnedgång inom 45 min förslag `djup 40` (vänta på mörkret). Navigatörens `stjärnfix`
  (`StarFix`, 4 min): solen −3 till −11° ⇒ stjärnor σ 0,05; natt med månljus ≥ 0,4 ⇒ månen σ 0,15; genom
  periskopet × 1,5 (krav som för fix), på bemannad brygga sextanten; annars nej med skäl. Föreslås i skymning
  och gryning när besticket > 0,25 nm. Vanlig `fix` i periskopet är oförändrad (σ 0,1 dygnet runt). Ja-boten
  i kuba, jagad och sundet: samma utfall före och efter D1–D4.
- **Molnen** (`Environment.clouds`, `Clouds`; Clyde N2): molntäcket 0–1 (`cover`), utom i uppklarningarna
  (`breaks`, simtid från–till, `break_cover` 0,2). `Light.cloud` släcker månljuset med 85 % vid helt täcke
  (`CLOUD_MOON_F`: mörkare natt, färre siluetter, kortare nattsikt). Från 0,6 (`CLOUD_STARS`) säger navigatören
  att molnen täcker himlen: ingen stjärn- eller månfix (`_star_method`, han ser uppåt i periskopet; almanackan
  vet inget om moln). Utan `clouds` klar himmel som förut. Clyde: täcke 0,75–0,95 med en uppklarning på
  10–25 min var 1,5–3:e timme.
- **Fyrarna** (`seabed.Lighthouse`, `Environment.lights` = de som lyser, `Scenario.light_list` ⇒
  `Knowledge.lights` = fyrlistan; Clyde N3): med fyrlista gäller fyrarna i nattfixen (`_start_light_fix`).
  En fyr syns inom sin lysvidd om inget land ligger emellan (`light_visible`, prov var 0,1 nm, strandkanten
  vid fyren räknas inte). Två eller fler i sikte: korsbäring σ 0,1 nm på 45 s; en: bäring och avstånd ur
  kimningen σ 0,2; ingen: ingen fix ("inga fyrar syns härifrån"). Dagtid landmärken som förut. Navigatören
  föreslår periskopfix på natten bara när kortet säger att någon fyr borde synas från besticket
  (`lights_expected`), annars fix mot botten om botten är brant nog. Clyde: Pladda, Holy Isle, Lady Isle,
  Little Cumbrae, Toward Point och Cloch Point.
- **Firth of Clyde** (`seabed.Firth`, `clyde_seabed`; N4): vatten bara i bassängerna (mittlinje med halv
  bredd och mittdjup per punkt, väggar som stupar som djup · (1 − u⁴)), land runt om; den första bassängens
  södra ände går ut ur kortet. Öarna är ellipser med brant strand (8 m + 400 m/nm). Kortet (40 × 40 nm,
  Pladda i (14; 4)): Arran som ellips, Arrandjupet ~150 m, västra rännan mellan Bute och Great Cumbrae
  ~3,5 nm och 60–80 m, Largs-rännan öster om ön under 1 nm och 30–45 m, sedan ~3 nm brett förbi Toward
  och Dunoon, Holy Loch en grund vik (10–28 m) västerut. Djupen ±8 % med fröet. Sjökortet (`chart_copy`,
  0,1 nm) är det noggranna brittiska kortet: stränder och öar flyttade ~0,1 nm, djupen ±5 %.
- **Is:** `ice.py` är sanning (bara isekolodet i `navigation/ice.py`, mastkontrollerna
  `masts_clear` och periskopets `ice_view` läser den); `icemap.py` är kunskap, byggd av `IceSounded` med
  beräknad position. Öppningars kvalitet = lägesosäkerhet (växer 8 m/min) mot
  halva längden. Isekolodet lodar också för och akter (50 m från tornet; `_hull_ice`,
  `hull_clear()`): ytläge (vid stationen eller genom nyis) föreslås bara när båda visar is vi kan
  bryta. Annars står tornet i kanten eller på tvären: `nav.vak.reposition` och tillbaka mot öppningens
  mitt, högst `VAK_TRIES` (2) gånger, sedan som en för smal öppning (`nav.vak.too_narrow` med `cramped`:
  "för- och akterskeppet har tjock is över sig", inte "för smal" om en råk som är lång nog). Periskopdjup
  kräver bara tornet. Nödblåsning mot is vi inte kan bryta tar slut där (`ice.bump` med `blow`: "Nödblåsningen är
  slut, vi vädrar tankarna"), och trimmen tar oss 5 m ned; förut blåste den tills ytan, som aldrig kom, och båten
  låg fast mot isen med beordrat djup 0 (2026-11-25). `nav.suggest.ice_closing` (djup 60, larm) kommer när isen ovanför blir tjock nära
  ytan, och också medan vi stiger mot en öppning (beordrat ≤ antenndjup), eller på väg mot ytläge när för-
  eller akterskeppet fått is vi inte kan bryta (isen driver medan vi stiger). Den öppningen stryks då
  (`OpeningNotFound`, `_surfacing_through`) och föreslås inte igen (2026-11-23; arktis frö 13: samma nyis tre
  gånger medan röken tätnade). `vak` går tillbaka till en öppning vi lämnat de senaste 90 s (`JUST_PASSED_S`,
  `just_passed_opening`; "stoppa här" kom under en 30 m råk med öppet vatten och ordern när vi glidit förbi), och
  tar en öppning som dög för en minut sedan om ingen duger nu (maskins förslag om en öppning, 20 s senare
  "ingen öppning loggad"). `vak` under en råk i fart (över 1,8 kn; 2026-11-24, arktis frö 21: stopp i 5 kn, ~130 m
  glid förbi, ut 250 m och vänd, fyra försök på 16 min) stoppar inte på stället: navigatören saktar till 1,5 kn
  (`VAK_MEASURE_KN`) rakt över (`nav.vak.measure`), och när isekolodet ser slutet back 2 kn till mitten
  (`nav.vak.measured`, `_measure_opening`, `_back_to_centre`; omkastningen först under 2 kn, så den inte hörs).
  Nyis kortare än båten (`MIN_SURFACE_LEN_M`) är inte värd att backa till: `nav.vak.too_short` och nästa öppning,
  eller sök vidare i 3 kn. Öppningen isen driver in över medan vi ligger stilla stryks (`OpeningNotFound`).
  Står vi nästan stilla under en sådan bit nyis går `vak` till den bästa loggade öppningen (den maskin nämner).
  Längre än 250 m (`LONG_OPENING_M`): stopp där vi är. Slår kaptenen back under mätningen (fortare stopp, hörs)
  gäller vaken: stopp i mitten om slutet är sett, annars när farten framåt är borta (`nav.vak.back_ordered`).
  Arktis ja-boten (8 frön): stationen nådd 5 ⇒ 6, arktis-kort 2 ⇒ 3. Maskin säger inte "vi har ingen öppning" de första 5 min efter att ha föreslagit en.
  Mätt (arktis-kort, ja-boten efter 1/5/20 s, 16 frön): stötar efter ytläge 7 ⇒ 3, "tjock is" efter
  ytläge 7 ⇒ 1, stationen nådd 17 ⇒ 13 av 48 (omläggningarna tar tid).
  Under isen föreslår ingen något annat medan ett förslag står obesvarat (2026-11-24, arktis-kort frö 3): maskins
  "gå till öppning N" (`eng.suggest.vent_vak`) inte medan ytläge eller periskopdjup föreslagits, navigatörens "sök
  vidare" (`nav.suggest.resume`) inte medan någon annan öppning föreslagits.
- **Havsbotten:** `seabed.py` är sanning (`Environment.bottom_at`; bara ekolodet läser den).
  Scenariot ger också `chart_seabed`, det gamla sjökortets bild (`Seabed.chart_copy`:
  formerna flyttade, ingen ojämnhet, ibland utan berg) som blir `Knowledge.bathymetry`.
  Navigatören ritar djupkurvor ur den och loggar kortets djup längs besticket.
  Botten dras sist i scenariot så att övriga slumpdragningar inte flyttas.
  Bottenkontakt (`seabed.bottom_contact`, efter förflyttningen): ≤ 2 kn sätter sig kölen
  utan skador, annars grundstötning (skrov −0,015·fart, sonar/roder efter var, läcka > 5 kn);
  trimmen tar oss 15 m upp. Redan i kontakt får ett steg som inte gör det värre gälla (gör giren
  det värre gäller förflyttningen med förra kursen), så att båten kommer loss; trycker båten mot land
  står den still (farten genom vattnet 0, besticket glider inte) och maskin säger `bottom.pressed`
  var 2:a min; `bottom.touch` högst en gång per minut. Navigatören (`_shoal_watch`, var 20:e s) ser på kortet 6 min
  framåt (minst 1 nm) ± bestickets σ åt sidorna, och en färsk lodning; föreslår djup
  30 m över botten. `NavigationStation.depth_limit()` begränsar sonarens djupförslag.
  Står besticket på kortets land (kortets strand ligger fel, upp till `accuracy_nm`) föreslår
  navigatören kursen med kortaste väg till kortets vatten (`water_dist`, `nav.suggest.chart_land`,
  larm). Plottets ben prövas mot kortet (`course_safe`: inget land närmare än `LAND_SAFE_NM` 0,5 nm,
  eller på kortets land mot närmaste vatten); annars giren åt andra hållet, annars inget förslag.
  Lotsen (`pilotage.py`, sanning, efter AI:erna i varje tick): andra fartyg än vårt prövar vägen
  mot den beordrade kursen (giren åt kortaste hållet med girhastigheten, sedan rakt) 3 min framåt
  (minst 0,25 nm); leder den grundare än 10 m (ytfartyg) eller 15 m under kölen (ubåt) väljs
  närmaste kurs i steg om 10° vars väg är fri, annars den djupaste. Bara där det finns land
  (sundet, övningen); på vanlig väg girar den sällan (fingeravtrycket ändrades bara i sundet-in/1,
  patrullbåten i farleden; kontrollen oförändrad).
  `kurs mot banken` (`SteeringMixin._steer_to_bank`, i scenarier vars sjökort har en `Bank`): kurs mot
  närmaste punkt där kortet visar `BANK_MIN_M`–`BANK_MAX_M` (60–250 m, att lägga sig på), sökt var 5:e grad
  ut till `BANK_LOOK_NM`; står vi redan där säger navigatören det (`nav.steer.bank_here`). Navigatören
  föreslår inte botten under ett pågående anfall (`Knowledge.charged_close`, se Besättningen under jakt).
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
- **Strömmen** (`navigation/current.py`, `CurrentMixin`; sanningen är `Environment.current_set`/`current_kn`
  och tidvattnet): vid varje fix (`_apply_fix`) är restfelet i besticket sedan förra fixen, delat med tiden,
  en mätning av strömmen besticket missat; osäkerheten är två fixars σ och 2 % av den gångna vägen (logg och
  gyro). Bara med minst 20 min mellan fixarna och ingen tid på botten. Kalman per axel (start σ 0,5 kn,
  strömmen får ändra sig 0,01 kn²/h); kvalitet ur σ (0,05/0,1/0,25 kn). Från osäker räknar besticket med
  strömmen; från god växer bestickets osäkerhet hälften så fort (`CURRENT_GROWTH_FACTOR`). Navigatören säger
  `nav.current` första gången och när den ändrat sig ≥ 0,15 kn eller 30°; `ström` ger läget; panelen
  NAVIGATION har raden Ström. Mot sanningen (`tests/test_current.py`, kuba, 0,4 kn, fix var 25:e min i 3 h,
  8 frön): medianfel < 0,15 kn, besticket en timme efter sista fixen ~0,66 av felet utan strömmen. Arktis med
  ja-boten: drivstationen 4 ⇒ 6 av 8 (`kontroll.py`, ny baslinje).
- **Sjögången** (`Environment.sea_state`, Beaufort 0–7; V1–V4 2026-11-19). Grov sjö är dålig för
  båda sidor: vi hör och ser sämre, men jagarens sonar och flygets radar också. Scenarierna: arktis och
  duell 1 (under isen gäller isens brus), övning och sundet 2, kuba och jagad 3, konvoj 5 (höjd från 4).
  - Havsbrus (`sea_noise_db`): `noise_at` = `background_noise` + 2,5 dB per Beaufortsteg från 3
    (background_noise gäller vid 3; övningen och sundet fick 64,5/66,5 dB så att de är oförändrade vid 2).
    Gäller vår sonar, jagarens passiva lyssning och bojarna; inte under isen.
  - Jagarens ping (`sea_ping_loss_db`): 3 dB förlust per steg från 5 (bubblor under kölen, rullning).
  - Radar och utkik mot masterna (`radar_clutter_f`): sjöklotter, räckvidden ×1 till och med 3, ×0,5 vid
    4, ×0,35 vid 5, ×0,25 vid 6 (flygets `RADAR_MAST_NM`, jagarens `MAST_NM`); i ytläge mindre (×0,8 vid 5).
  - Sikten (`SEA_VIS_F` i `Environment.light`): ×0,8 vid 5, ×0,6 vid 6, ×0,5 vid 7 (sjörök, regnbyar).
  - Vågtopparna (`periscope.WAVE_M`, signifikant våghöjd 0,6 m vid 3, 2 m vid 5, 3 m vid 6) skymmer lika
    mycket till av fartyg (`detectable`, `visible_part`) och händelser (`event_visible`): små båtar och
    plask försvinner tidigare, skrovet går under horisonten tidigare. Bedömningarna (`sea_sigma_f`):
    avståndets och kursens σ ×(1 + 0,1 per steg över 3), både periskopet och bryggan; kvaliteten följer σ.
  - Sjön suger (`OwnShip.heave_amplitude`, `_heave_step`): från 4 drar vågtrycket båten mot ytan i takt
    med sjön (period 5 + B s). Utslaget 2,4 m per meter våghöjd i ≤ 2 kn på periskopdjup, ×(1 − 0,12 per
    knop över 2, minst 0,3), avtar under 18 m med e-faldning 10 m. Kölen grundare än 13 m (`BROACH_DEPTH_M`)
    ⇒ tornet bryter ytan (`broach`, larm från centralen) och syns 15 s som en ubåt i ytläge för flyget och
    jagaren (`OwnShip.broached`). Vid 5 och periskopdjup (17 m) bryter det i ≤ 3 kn, inte i 6 kn; vid 6
    behövs ~6 kn, vid 7 ~7 kn (högsta fart med masten uppe). Trimmaren ser utslaget på djupmätaren
    (systemtavlan "Sjön suger"), räknar om det till det beordrade djupet på väg upp och föreslår
    `fart N` eller `djup 25` när marginalen till ytan är under 1 m (`trim.heave`, larmförslag).
  - Periskopet sköljs över (`periscope.crest_m`): vågtoppen (0,8 × våghöjden) når över ögat (1,5 m plus
    sjöns sug) en del av tiden; de sekunderna ser okularet inget. Vid 5 ~10 %, vid 6 ~30 % av tiden.
    `off.periscope.washed` en gång per hissning.
- **Vädret** (`sim/weather.py`, `Environment.weather`; V5 2026-11-19): sjögången ändras ett steg i taget,
  högst var 30–60:e minut, mot prognosen (`trend`: från vilken tid vilken sjögång) med sannolikheten 0,6,
  bort 0,1; vid prognosen ett steg åt vardera hållet 0,2. Inom `lo`–`hi`. Egen slumpström
  (`Game.rng_for("weather")`); `World.tick` sätter sjögången först. Kuba 3 → 4 efter 2 h (2–5), konvoj 5
  (4–6); övriga scenarier har fast sjö. Prognosen står i ordern (`VÄDER:`), sanningen kan avvika.
  Besättningen märker det med sina instrument: bryggan (`bridge.sea`), periskopet vid nästa titt
  (`off.periscope.sea`), sonaren när havsbruset ändrats ≥ 2 dB (`sonar.ambient`, läses var 60:e s, inte
  under isen) och trimmaren när djupmätaren börjar slå (Sjögången ovan).
- **Regn och dimma** (`weather.Showers`, `Environment.showers`; 2026-11-25): episoder som kommer och går (egen
  slumpström `Game.rng_for("showers")`, `rain_per_h`/`fog_per_h`, 15–60 min). Regn höjer havsbruset 3–8 dB
  (`Environment.noise_at`) och ger klotter på jagarens radar mot master (`RAIN_RADAR_F` 0,7); sonar hör det börja och
  sluta (`sonar.rain`). Dimma sätter sikten till 0,2–0,8 nm dag som natt (`Environment.light`): periskopet säger det
  när det hissas, bryggan när dimman kommer och lättar (`bridge.fog`), och handelsfartygen blåser i mistluren varannan
  minut (`Transient("foghorn")`, 150 dB, hörs bara nära i vattnet; `sonar.foghorn`). Radarn ser genom dimman. Per
  scenario: kuba regn 0,25/h, jagad 0,2, konvoj och krig regn 0,2 och dimma 0,08, Clyde 0,3 och 0,15, sundet 0,1
  och 0,2, övning och svansen 0,15 och 0,05, Arktis och duellen dimma 0,1.
- **Vrak** (`seabed.Wreck`, `Seabed.wrecks`, `place_wrecks`; 2026-11-25): två vrak på kubabanken (tankfartyg och
  fraktfartyg sänkta 1942), två på kustbanken i sundet, tre i Clyde; egen slump ur scenariots värden. Kortet
  (`chart_copy`) har de flesta (`WRECK_UNCHARTED_P` 0,25 saknas), lite fel i läget, ritade som Ш och kända platser
  (`Knowledge` gör dem till `Waypoint`, "vraket"/"vrak 1" …, `kurs mot vraket`). Ekolodet rakt över ett vrak
  (`WRECK_ECHO_NM` 0,04) ser ett föremål; står ett vrak på kortet inom 0,8 nm från besticket blir det en fix
  (`nav.wreck`). En ubåt på botten inom 0,1 nm från ett vrak smälter ihop med dess eko (`WRECK_CLUTTER_DB` 8 dB
  mer i jagarens och bojarnas aktiva sonar). Jagade föreslår navigatören kurs mot ett vrak på kortet inom 2 nm på
  ett djup vi kan ligga på, och vid vraket botten (`nav.suggest.wreck`, `wreck_settle`).
- **Fisket** (`sim/fishing.py`; 2026-11-25): trålare (`Trawler`, kind fishing) på bankerna i kuba (tre), jagad (två)
  och sundet (två), och i kuba en sovjetisk spaningstrålare (kind spytrawler), som jagaren skuggar en halvtimme av
  varje och en halv (`DestroyerAI.shadow`, sista 30 min av 90). Trålen går 0,25 nm akterut på 60 m (bottentrål
  5 m över botten där det är grundare); vajern från aktern ned dit. Går tornet eller skrovet genom den fastnar vi
  (`trawl.caught`): framdrivningen −0,15, farten ned, fiskaren ropar på radion (jagare inom 12 nm får ett läge,
  σ 0,5 nm); 30 s fart framåt sliter vajern (`trawl.free`). Sonar säger när en fiskebåt trålar (`sonar.trawling`).
  Fiskelamporna syns 6 nm på natten (inte i dimma; periskopet och bryggan). Fiskebåtar räknas inte som hot
  (`ContactTrack.benign`); spaningstrålaren är vänlig för plottet men torpedrummet varnar för den.
