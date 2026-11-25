# Vyerna

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

- **Huvudskärmen** (`GameScreen` i `ui/app.py`, 2026-11-24): statusraden, översikten (`OverviewPanel` i
  `ui/widgets.py`, ritad varannan halvsekund medan den syns) och under den loggremsan med djupmätaren bredvid,
  9 rader från 100 × 30 (`BIG_MIN`, klassen `big`), annars 7. `Esc` och `översikt` går tillbaka hit
  (`SubApp._overview_word`). Översikten är ingen vy i Tab-ordningen (sedan 2026-11-25; förut var den det i små
  fönster, där loggen var huvudskärm). `ReportLog.emit` sparar raderna (`entries`) och speglar dem till
  loggboken när den är nere (`mirror`); skriv aldrig loggrader med `write`.
- **Loggboken som lager** (`ui/logdrawer.py`, `LogDrawer`, 2026-11-25; förut vyn `LogScreen`): PageUp i vilken vy
  som helst (också huvudskärmen, inte hytten) fäller ned hela loggen över vyns nedre 70 % ovanför orderraden
  (`overlay: screen`, `place()` efter höjden; Textuals `position: absolute` ensam tog plats i layouten). Den står
  sist; PageUp en sida bakåt, PageDown framåt och förbi slutet upp, `Esc` (tom orderrad: `OrderLine`, på
  huvudskärmen appens binding) upp. Orderraden behåller fokus, så order går att ge med loggen nere. `logg`
  växlar, `telegram` visar bara remsorna (`DrawerLog.only_telegrams`), slutrapporten fäller ned den i full höjd.
  Ingen bokstav: orderraden tar alla (`läget`, `länsa` …). Mellanslag växlar inte filter (vyerna använder det).
- **Loggen** (`ReportLog` i `ui/widgets.py`, en `RichLog`): `min_width` 20, så raderna bryts efter panelens
  bredd; `RichLog`s standard 78 klippte loggen i fönster upp till ~100 kolumner (80×24: ord saknades).
  En rapport med färdiga rader (`data["table"]`, `table_header`) får en tabell under raden; den läses upp bara
  med `data["spoken"]` (svepet). Svepet (`stations/sweep.py`, 2026-11-23): periskopet, bryggan, radarn och den
  aktiva sonarn samlar utropen i ett svep; fyra eller fler blir en rad (hur många, närmast, örlogsfartygen) och
  en tabell (kontakt, vad, bäring, avstånd, kurs och fart), färre sägs var för sig som förut. Sonars "hörs igen"
  samlas som de tappade (`sonar.regained.many`).
- **Översikten** (`översikt`, `lägesbild`; `sim/overview.py`, `ui/overview_render.py`, `ui/overview.py`,
  2026-11-24): allt kaptenen vet på en skärm; huvudskärmen (i alla fönster sedan 2026-11-25). Vänster spalt (55 %, från
  `TWO_COL_W` 90 kolumner, så att huvudskärmen i 100 kolumner har två): sjökortet kring vårt beräknade läge i den minsta skala som rymmer plottets lösningar
  på de hållna kontakterna (minst 3 nm åt varje håll, `chart_scale`), vattenfallet 10 min och djupprofilen, ritade av
  vyernas egna renderare. Höger spalt: kontakttabellen, lägesraderna med bäringsrepeatern bredvid (gyrot med
  plottets hållna kontakter, numret i slagets färg, flyttad från centralen) och systemtavlans paneler
  (`render_compact_panels`, oroliga först). Smalare: höger spalt och sedan sjökortet.
  `Station.overview_items()` ⇒ `Game.overview()` (`OverviewView`, byggd en gång per läge som de andra):
  plottet ger en `ContactRow` per kontakt med bäring (tappade i 30 min, sjunkna inte): klassningens första led,
  senaste bäringen och dess ålder, operatörens bäringsdrift (▸ höger/medurs, ◂ vänster, °/min, från 0,3; `drift`), och där sjökortet visar lösningen (≥ osäker, hot, handel eller eget) den
  framräknad till nu (bäring, avstånd, kurs, fart) med kvaliteten; plottet räknar inte om lösningen för vyn
  (`test_reading_the_overview_does_not_change_the_game`). Lägesrader (`Line`): vakthavande UPPDRAG (ordern ur
  `Knowledge.order_tasks`, tiden ut och kvar, varning under 30 min; "fienden har oss" fara, "fiende i närheten"
  varning), radion "Samband" under UPPDRAG (öppet nu och till när, varning; annars nästa tillfälle och om hur länge),
  periskopet PERISKOP (gradring, svep/titt/håller, förstoring; förr på centralens golv). Smal kontakttabell (under
  60 tecken, `COMPACT_W`): klassningen kortas först, lösningen kort, kvaliteten och tappad (∅) alltid med, i linje. Nytt system
  syns här genom att ge `Line` ur sin kunskap.
- **Sjökortet**: `Station.chart_items()` ger ritelement (`sim/chart.py`) ur
  kunskapen i beräknade koordinater; `Game.chart()` samlar, `ui/chart_render.py`
  rastrerar (en rad = två kolumner i höjd). Blyertsmärken (`PlotTeam.pencil`, ur `SoundHeard`, och ur `EventSighted` när bryggan eller periskopet
  såg plasket eller pelaren: då där det syntes, bäring och bedömt avstånd från vårt beräknade läge):
  ping `P`/`PP` (snabb), boj `B`/`BP`, plask `✕`, detonation `✱`, övning `○`, brytljud `↓`; en sjunken
  kontakt `×` där plottets lösning trodde att den var när den sjönk (`PlotTeam._sunk_at`, ritas `FORGET_S`); på kontaktens
  lösning om den är ≥ osäker, annars ett streck 0,6 nm längs bäringen från vårt beräknade läge. Samma
  märke och källa (beteckning eller 15°-sektor) högst var `PENCIL_GAP_S` (ping 5 min); skarpt första
  minuten, blekt efter 10, borta efter 30; klockslag bara på de 5 nyaste. Egna handlingar (`OwnSoundMade`,
  `OwnActionLogged` från radion och periskopet, inte kikaren) där vi trodde att vi var: `!` aktiv ping,
  `≋` skenmål, `▲` nödblåsning, `R` rapport, `⊙` periskop (högst var 5:e min). Egna torpeder
  (`TorpedoRoom.chart_items`): från avfyrningspunkten (beräknad) längs inställd kurs så långt de hunnit,
  `+` varje minut, huvud `•`/`✱` detonation (träff eller i förtid, `torp.run.early`)/`?`, kvar 30 min (`finished`); girad målsökare också med hörd bäring.
  Besticket får `◦` var 10:e min på klockan (`dr_ticks`), klockslag varje halvtimme. Kontakter: `»` först
  hörd (bäringen, en gång per beteckning) och `∅` tappad (lösningen ≥ osäker, annars senaste bäringen;
  inte isljud/civila), alltid med beteckningen. En tappad kontakt som återfinns har ingen lösning förrän
  plottet räknat om (högst 30 s): den gamla kastas (`Knowledge.on_detection`). Etiketter: högre lager vinner där de krockar, inom ett
  lager den som kom först (stationerna lägger det nyaste först); den som förlorar flyttas en rad upp
  eller ned (`LABEL_SHIFTS`) och försvinner bara om det är fullt där också (blyertsmärkets symbol, t.ex.
  `»`, är en del av etiketten). Teckenförklaringen har en tredje rad. Linjer (spår, djupkurvor, kust, farled streckad, bäringar,
  vektorer, osäkerhetsringar streckade) ritas i braille i prickskiktet `ui/canvas.DotLayer` (prickkoordinater
  2 per kolumn, 4 per rad); märken, etiketter, rutnät och gräns är hela tecken; högst lager vinner per ruta.
  Solfjädern (`PlotTeam._fan_items`, stil `fan`): för det markerade målet (det kaptenen senast frågat om
  med `S-1`, `plot S-1` eller `läge S-1`, `PlotTeam.marked`) plottets bäringar på nuvarande ben (sedan `tma_from_t`),
  högst `FAN_LINES` (10), dragna från `own_x`/`own_y` där vi trodde att vi var; med en lösning ≥ osäker så
  långa som 1,4 × avståndet då. Nästan parallella linjer visar varför avståndet är osäkert. Nytt system ritar sig självt.
  Sedan 2026-11-25 också kortets vrak (Ш, "vrak") och blyertsmärkena h (reparation) och X (kollision).
- **Sonarvyn** (`sonar`, `vattenfall`; `sim/sonar_view.py`, `ui/sonar_render.py`, `ui/sonar.py`): vattenfallet,
  bäring vågrätt (sann, eller relativt fören ur navigatörens kurslogg) och tid lodrätt, nyast överst, 10/30/60 min.
  `Station.sonar_items()` ⇒ `Game.sonar()` (`SonarView`), bara kunskap: sonarrummet ger bäringsspår ur
  `ContactTrack.observations` (källorna sonar/ping/aktiv; prickarna bredare efter `se`), hörda transienter med
  bäring (`HeardMark`; pingar bara där inget annat står; etiketterna med en ledig ruta före och efter), tappade (`∅`), egna ljud i marginalen och en rad per
  kontakt (bäring, operatörens bäringsdrift över 3 min, lösningens kvalitet, klassning); torpederna sonar hör
  (`TorpedoTrace`): fientliga ur sonarrummets bäringar (`torped 1`, starkast färg, över alla spår), våra egna ur
  torpedrummet med tubens nummer (`tub 2`, dämpade), etiketten dämpad när sonar tappat dem; plottet lösningens
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
- **Ubåten** (`ubåt`, även `profil`/`system`; `ui/boat.py`, `ui/boat_render.py`; genomskärningen med vattnet i
  varje avdelning efter hur full den är, `Compartment.water`, och gula skott när de är stängda, `Flooding.closed`,
  2026-11-25; panelen MASKIN visar läckorna per avdelning, länspumparna, skotten och provdjupet, SKADOR vad som
  lagas, tyst, "mer går inte till sjöss" och "under vatten"; förklaringen bryts mellan posterna efter bredden,
  `pack_legend`, 2026-11-25): djupprofilen och
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
  bruten axel; vårt djup, kortets botten och tunna nivåer i braille vid exakt djup) och djupmätaren bredvid loggen. Tab växlar (hytten, när starpom har befälet) → central → sjökort → sonar →
  ubåten → utsikten → översikten. Utsikten (`ui/lookout.py`, `LookoutScreen`, 2026-11-25; förut två vyer) visar
  bryggans panorama när bryggan är bemannad (eller luckan på väg) och periskopet nere, annars periskopbilden;
  vyns tangenter (`EMPTY_KEYS`, en egenskap) följer det som visas. Vyerna, orden som öppnar dem och Tab-ordningen står i registret `ui/views.py`
  (`REGISTRY`, `ViewDef`, `tab_order`); `SubApp` slår bara upp där.
- **Centralen** (`central`, Tab först i stort fönster; `ui/central.py` `CentralScreen`, `ui/central_render.py` scenen,
  `ui/central_instruments.py` instrumenten): bild av центральный пост på hela skärmen (2026-11-24; förut huvudvyn och
  en liten bild bredvid loggen). Bara egna instrument (`StatusSnapshot`) och vem som talar, aldrig kunskapen om andra
  fartyg (bäringsrepeatern och periskopets gradring står i översikten; `test_no_contacts_in_the_central`). Inga
  besättningsfigurer (avslaget): den som talar syns på snabbtelefonens panel under vänstra pulpeten (`PHONE`, en
  lampa med namn per station i rollens färg i 3 s). Två storlekar: från 100 × 22 (`BIG`, `Geometry.slots`)
  är väggarna instrument i braille (`ui/canvas.py`: `Braille` 2 × 4 prickar per ruta, stil efter prioritet;
  `ui/instruments.py`: `Dial`, `draw_dial`; `central_instruments.draw_instruments`): gyro, sidroder (±35°),
  telegraf (handtag = beordrad fart, gul visare = maskinens svar, läget B längst till vänster = back),
  djup 0–500 m med prov- och krosszon, fart 0–30 kn med kavitationszonen (6 + djup/25), klocka, djuproder
  med libell; på en hög vägg (≥ `TALL_ROWS` 22 rader, `Geometry.strip_rows`, ~30 % av höjden) en rad mindre
  instrument under: LUTNING (дифферент ±10°, `pitch`), TRIM (rodrens last, lätt–tung, `plane_load`), BATTERI
  (0–100 %, rött under 20, "urladdning" utan reaktor) och LÄNS (vatten i båten 0–60 t, `flooding`); där står också
  klockan, så att fartmätaren får hela rutan (låg vägg: fart och klocka sida vid sida). Mätarnas etiketter som
  skulle krocka med en tidigare ritas inte (`draw_dial`). Avläsningen är
  exakt; visarna följer med tröghet (`Needles`, τ 0,5 s, kursen den korta vägen) och ritas tio gånger i sekunden
  (`CENTRAL_EVERY_S`). Mellanstorleken (helskärm i ett 80 × 24-fönster, bilden minst `READOUT_MIN_H` 16 rader men mindre än `BIG`,
  2026-11-25) har instrumentens namn och avläsning som rader på väggarna (`draw_readouts`, `READOUT_WALLS`: gyro,
  sidroder, telegraf, lutning, trim; djup, fart, djuproder, batteri, läns, klocka). Den lilla bilden (bredvid loggen) är bara rummet: rör med ventilrattar, tre lampor för
  snabbtelefonen, telegrafens och julgranens lampor. Ren funktion `render_central(status, speaking, t, width, height,
  shown)`, vem som rapporterat senaste 3 s ur `SubApp._spoke`. Rodren härleds ur beordrat mot verkligt
  (`rudder_angle`, `plane_angle`), periskopet hissas med `periscope_up_s` och okularet vrids efter bäringen relativt
  fören (`eyepiece`: handtagen rakt förut, pil åt sidorna, linserna akterut), stegen och luckan (himlen syns),
  maskintelegrafen (`telegraph_lamp`),
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
  Kärnvapenrådet på tavlan: VAPEN "Kärnladdning" (säkrad / rådet samlas / nycklar 3/3, skarp N min), bara när
  T-5 finns ombord (`stations/council.py`, se `docs/system/besattning.md`). Sonaren säger om sjunkbomberna
  "troligen signalsjunkbomber, eller skarpa långt bort" när den inte kan avgöra (kvaliteten i loggen).
