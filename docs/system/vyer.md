# Vyerna

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

- **Sjökortet**: `Station.chart_items()` ger ritelement (`sim/chart.py`) ur
  kunskapen i beräknade koordinater; `Game.chart()` samlar, `ui/chart_render.py`
  rastrerar (en rad = två kolumner i höjd). Blyertsmärken (`PlotTeam.pencil`, ur `SoundHeard`, och ur `EventSighted` när bryggan eller periskopet
  såg plasket eller pelaren: då där det syntes, bäring och bedömt avstånd från vårt beräknade läge):
  ping `P`/`PP` (snabb), boj `B`/`BP`, plask `✕`, detonation `✱`, övning `○`, brytljud `↓`; på kontaktens
  lösning om den är ≥ osäker, annars ett streck 0,6 nm längs bäringen från vårt beräknade läge. Samma
  märke och källa (beteckning eller 15°-sektor) högst var `PENCIL_GAP_S` (ping 5 min); skarpt första
  minuten, blekt efter 10, borta efter 30; klockslag bara på de 5 nyaste. Egna handlingar (`OwnSoundMade`,
  `OwnActionLogged` från radion och periskopet, inte kikaren) där vi trodde att vi var: `!` aktiv ping,
  `≋` skenmål, `▲` nödblåsning, `R` rapport, `⊙` periskop (högst var 5:e min). Egna torpeder
  (`TorpedoRoom.chart_items`): från avfyrningspunkten (beräknad) längs inställd kurs så långt de hunnit,
  `+` varje minut, huvud `•`/`✱` träff/`?`, kvar 30 min (`finished`); girad målsökare också med hörd bäring.
  Besticket får `◦` var 10:e min på klockan (`dr_ticks`), klockslag varje halvtimme. Kontakter: `»` först
  hörd (bäringen, en gång per beteckning) och `∅` tappad (lösningen ≥ osäker, annars senaste bäringen;
  inte isljud/civila), alltid med beteckningen. Etiketter: högre lager vinner där de krockar, inom ett
  lager den som kom först (stationerna lägger det nyaste först); den som förlorar flyttas en rad upp
  eller ned (`LABEL_SHIFTS`) och försvinner bara om det är fullt där också (blyertsmärkets symbol, t.ex.
  `»`, är en del av etiketten). Teckenförklaringen har en tredje rad. Linjer (spår, djupkurvor, kust, farled streckad, bäringar,
  vektorer, osäkerhetsringar streckade) ritas i braille i prickskiktet `ui/canvas.DotLayer` (prickkoordinater
  2 per kolumn, 4 per rad); märken, etiketter, rutnät och gräns är hela tecken; högst lager vinner per ruta.
  Solfjädern (`PlotTeam._fan_items`, stil `fan`): för det markerade målet (det kaptenen senast frågat om
  med `plot S-1` eller `läge S-1`, `PlotTeam.marked`) plottets bäringar på nuvarande ben (sedan `tma_from_t`),
  högst `FAN_LINES` (10), dragna från `own_x`/`own_y` där vi trodde att vi var; med en lösning ≥ osäker så
  långa som 1,4 × avståndet då. Nästan parallella linjer visar varför avståndet är osäkert. Nytt system ritar sig självt.
- **Sonarvyn** (`sonar`, `vattenfall`; `sim/sonar_view.py`, `ui/sonar_render.py`, `ui/sonar.py`): vattenfallet,
  bäring vågrätt (sann, eller relativt fören ur navigatörens kurslogg) och tid lodrätt, nyast överst, 10/30/60 min.
  `Station.sonar_items()` ⇒ `Game.sonar()` (`SonarView`), bara kunskap: sonarrummet ger bäringsspår ur
  `ContactTrack.observations` (källorna sonar/ping/aktiv; prickarna bredare efter `se`), hörda transienter med
  bäring (`HeardMark`; pingar bara där inget annat står), tappade (`∅`), egna ljud i marginalen och en rad per
  kontakt (bäring, operatörens bäringsdrift över 3 min, lösningens kvalitet, klassning); plottet lösningens
  förutsagda bäringar för benet (streckade i kvalitetens färg, på från början, ↑ döljer dem; neutrala kontakter, alltså handelsfartyg, isljud och drivstationen (`NEUTRAL_KINDS`), tonas ned: spår, lösning och kontaktrad dämpade, spåren under hotens där de korsar och hotens etiketter först, men inget döljs) och sina märkta girar (`‹gir`, högst
  var 5:e min); navigatören kursloggen (var 10:e s) och våra girar ≥ 15° (`↻`/`↺` och en svag linje). Vyn räknar
  inget själv och ger inga verktyg (designprincip 1). Tab-ordningen: sjökort → sonar → ubåten.
- **Huvudraden och sjögången:** kontakterna hot först i sitt slags färg (`StatusSnapshot.contact_kinds`,
  `track_kind`), hot blinkar när vi är jagade, resten `+n`; sonarpanelen räknar (`contacts_text`).
  Sjögången `Environment.sea_state` (Beaufort; Kuba 3, konvoj 5, sundet och övningen 2, Arktis 1) syns
  i bilden (`PeriscopePicture.sea_state`: vågornas täthet och längd, skum från 5, bryggans horisont
  gungar från 5) och när bryggan bemannas (`bridge.manned`); verkan på brus, sikt, radar och
  periskopdjupet står i `docs/system/hav.md` (Sjögången).
  Periskopet visar utkikens bedömda avstånd på remsan och under vattenlinjen (`range_tag`), ingen skala.
- **Ubåten** (`ubåt`, även `profil`/`system`; `ui/boat.py`, `ui/boat_render.py`): djupprofilen och
  systemtavlan i en vy. Genomskärningen överst (från `HULL_MIN_H` rader, annars avdelningarna som lampor
  på andra rubrikraden), profilen till vänster (60 %) och panelerna till höger; under `SIDE_MIN_W` (110)
  profilen över panelerna (högst halva höjden). Panelerna kompakta (`render_compact_panels`): fara och
  varning först och fullt, lugna paneler fälls efter `FOLD_ORDER` (torpedrören sist) till en gemensam rad
  sist, och räcker inte det visar de oroliga bara sina larm. Ryms panelerna inte i en spalt och det
  finns plats för två på minst `PANEL_COL_MIN_W` (48) tecken får profilen 45 % och panelerna två spalter,
  delade vid en panelrubrik. Tidsskalan är automatisk (`auto_time_zoom`): minsta skalan vars fönster rymmer
  hela historiken, så att spåret fyller profilen även i början; ←/→ väljer själv, mellanslag tillbaka.
- **Djupprofilen**: `Station.profile_items()` ger element (`sim/profile.py`):
  fasta djup (`Level`), navigatörens djuplogg (var 10:e s), ekolodets bottenlodningar
  (bara efter `ekolod`), isekolodets lodningar och sonarrummets hörda ljud. `Game.profile()`
  samlar, `ui/profile_render.py` ritar sidovyn (tid vågrätt, botten i eget band under
  bruten axel; vårt djup, kortets botten och tunna nivåer i braille vid exakt djup) och djupmätaren bredvid loggen. Tab växlar (hytten, när starpom har befälet) → logg → sjökort → sonar → ubåten → periskopbild → logg, med luckan öppen brygga före
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
  `draw_dial`): gyro, sidroder (±35°), telegraf (handtag = beordrad fart, gul visare = maskinens svar,
  läget B längst till vänster = back),
  djup 0–500 m med prov- och krosszon, bäringsrepeatern på gyrots ring (`repeater`: plottets hållna kontakter
  med `StatusSnapshot.contact_bearings` ur kunskapen, numret i beteckningen i slagets färg `CONTACT_STYLE`, hot
  överst; bara i stora bilden), fart 0–30 kn med kavitationszonen (6 + djup/25), klocka, djuproder
  med libell. Avläsningen är exakt; visarna följer med tröghet (`Needles`, τ 0,5 s, kursen den korta vägen)
  och ritas tio gånger i sekunden (`CENTRAL_EVERY_S`, bara när huvudvyn syns). Under `BIG` de små
  lådmätarna. Ren funktion `render_central(status, speaking, t, width, height, shown)`
  ur `StatusSnapshot` (egna instrument, och plottets kontakter på gyrot) och vem som rapporterat senaste 3 s (`SubApp._spoke`, roll ⇒
  plats eller snabbtelefonens lampa). Mätare kurs/sidroder/djup/djuproder (rodren härledda ur beordrat mot
  verkligt), periskopet hissas med `periscope_up_s` och okularet vrids efter bäringen relativt fören
  (`eyepiece`: handtagen rakt förut, pil åt sidorna, linserna akterut; stor bild: `PERISKOP 047 · titt · hög`
  under pulpeten), stegen och luckan (himlen syns), maskintelegrafen,
  julgranen (`openings`: lucka, periskop, radar, antenn, ventil rött när öppna, blåsning gult; liten bild
  lampor i rad, stor bild en tavla med namn under högra pulpeten), rött ljus på natten eller jagade (`night`, `hunted`), larmlampor,
  rök och vatten.
- **Systemtavlan**: `Station.system_items()` ger element (`sim/systems.py`):
  `Gauge` (panel, etikett, text, tillstånd ok/info/av/varning/fara, ev. stapel), `Compartment`
  (nio avdelningar, maskin), `TubeRack` (torpedrum), `Flooding`. Ur egna instrument
  (`own.sys`), aldrig om fienden. `Game.systems()` samlar, `ui/systems_render.py` ritar
  genomskärningen (skrov, torn, skott och vatten i braille, `HULL_ROWS` rader; avdelningarna som text) och panelerna (okända paneler hamnar sist, så nytt system ritar sig självt).
  Ryska skyltar (`ui/placards.py`): panelerna efter stridsavdelning (`PANEL_RU`: БЧ-5, БЧ-1 …, utelämnas när
  de inte får plats), vyernas rubriker (`view_title`, `VIEW_RU`: svenskan först) och mässingsskylten
  ЦЕНТРАЛЬНЫЙ ПОСТ i centralens tak när det finns plats före stegen. Ny panel eller vy: lägg till där.
  Sjögången på tavlan: TRIM "Sjön suger" (trimmaren, se `docs/system/besattning.md`).
