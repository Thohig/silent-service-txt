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
- **Is:** `ice.py` är sanning (bara isekolodet i `navigation/ice.py`, mastkontrollerna
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
