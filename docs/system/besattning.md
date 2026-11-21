# Radion, starpom och trimmaren

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

- **Radion och telegrammen:** allt radion tar emot publiceras som `TelegramReceived` (text, `kind`
  telegram/broadcast, mottagningsnummer ombord) ⇒ `Knowledge.telegrams`. Radiomannen säger bara att det
  kommit (`radio.message`, `radio.moscow`: `data["telegram"]` = numret, texten i `data["text"]` och
  `read_aloud`, som svenskt tal läser efter raden); loggboken skriver remsan under raden
  (`ui/strips.py`, `TelegramStrip`, bryts efter loggens bredd, högst `MAX_W`). Ordern är loggens första
  remsa (`SubApp._log_order`, kind "order"). `telegram` öppnar loggboken (`LogScreen(telegrams=True)`,
  alla fönsterstorlekar) med bara remsorna; mellanslag växlar till hela loggen, `logg` likaså. Radio Moskva (`sim/broadcasts.py`): `radio moskva` på antenndjup
  (masten fri, radion hel) ⇒ efter `LISTEN_S` (20 s) säger radiomannen en sändning för orderns datum
  (`order_day` ur `DATUM:`-raden, `broadcasts_for`); bara stämning, aldrig information. Den 28 okt bara
  bärvåg. Ljudet `shortwave` (menyns ratt och brus) före rösten.
  `radio` (`RadioStatus`, `_status_data`): ett sambandstillfälle som pågår och inte är avklarat ("pågår,
  från 09:00 till 09:20"), annars nästa som inte börjat, och hur många telegram som kommit (rätt böjt).
- **Sambandstillfällena och långvågen** (L1–L4, 2026-11-19; `stations/radio/`): staben sänder vid
  scenariots sambandstillfällen (`Scenario.radio_windows`, 20 min, kuba-kort 15). Det vi missar sänds om
  vid nästa (`radio.missed` säger när: `_next_window_clock`); efter sista tillfället når det oss inte.
  Mottagning (`_receive`): på antenndjup (≤ 30 m) med masten på 60 s (`RECEIVE_S`), eller på djupet på
  långvåg med flytkabeln, ≤ 50 m (`VLF_DEPTH`) och ≤ 5 kn (`VLF_SPEED`), på 300 s (`VLF_RECEIVE_S`).
  Radiomannen sköter kabeln själv (`radio.cable.out`, `RadioStation.cable`); fortare dras den under och
  mottagningen står still (`radio.cable.fast`, förslag `fart 3`); under is flyter den inte (`radio.ice`).
  Förvarningen `radio.prewarn_vlf` föreslår `djup 40` och/eller `fart 3` (det som behövs, `_up_order`) i
  stället för antenndjup; går vi beordrat fortare än 5 kn (följer, anfaller) föreslås antenndjup, eftersom
  masten tar emot i vilken fart som helst; kräver ordern en rapport (`report_required`) gäller antenndjup
  som förut (`radio.prewarn`). `up_depth()` säger hur grunt radion behöver oss (30 eller 50 m); sonar föreslår inte
  skiktet och starpom säger nej till djupare under tiden. Långvågens kvalitet (`_vlf_quality`, fasta
  regler): mörker, fart ≤ 3 kn och djup ≤ 40 m ger var sitt plus, två ⇒ hel; annars stympad: remsan
  med nummer "?" och oläsbara grupper (`garble`, 45 % ░, `rng_for("radio")`), `radio.garbled` en gång per
  fönster med skälen och förslag om djup och fart; radion lyssnar vidare och tar emot hela vid nästa
  försök (masten på antenndjup alltid hel). Stympat verkställs inte (flaggor, positioner). Vyerna:
  djupprofilen visar flytkabelns djup (nivån `┄ flytkabel`) medan ett tillfälle väntar och kabeln (`╎`,
  `profile.Cable`) när den är ute; systemtavlan "kabeln ute, n min kvar"; loggen "på långvåg".
- **Rapporten till staben** (`sim/dispatch.py`, kunskap; R1–R2 2026-11-19): `sänd rapport` (allt),
  `sänd kort rapport` (eget läge och det som hänt), `sänd rapport S-3` (en kontakt). Radiomannen sätter
  ihop `SentReport` ur kunskapen: bestick med σ, kontakter med lösning ≥ osäker (hot först, högst 5;
  isljud och drivstation utelämnas), konvojens baskurs, händelser sedan förra rapporten (foto, hörd
  torpedträff, jagade). Längden i femsiffergrupper (anrop 2, läge 2, kontakt 3, konvoj 2, händelse 1)
  ger sändningstiden i morse: 6 s + 4 s per grupp (kort rapport ~22 s, två kontakter ~46 s).
  `radio.sending` säger grupper, sekunder och pejlrisken (`RadioStation.risk`: stor vid ≥ 45 s eller
  hot i plottet ≤ 8 nm, måttlig vid ≥ 25 s eller ≤ 15 nm, kvalitet ur hotets lösning). Förslaget
  `radio.suggest.report` gäller kort rapport när hela vore stor risk men den korta inte. Sänd rapport ⇒
  `ReportTransmitted` (också avbruten, `complete=False`), `mission["reports"]`, och remsan ДОНЕСЕНИЕ i
  loggen (`telegram_kind` "outgoing"). Pejlnätet (`enemy.py`, `DF_*`): kortvågen sänds ut med sin längd
  (`Emission.duration`) när sändningen slutar eller avbryts; under 10 s pejlas den aldrig, över 25 s
  alltid, däremellan linjärt; datumets σ = 1,5 nm · √(30 s / längd), 0,7–3 nm.
- **Huvudstaben** (`sim/headquarters.py`, R3; ägs av radion, läser aldrig världen): vet bara vad vi
  sänt (`ReportTransmitted`, avbrutna räknas inte). Svarar vid nästa sambandstillfälle, efter
  scenariots telegram och högst `MAX_PER_WINDOW` (3) åt gången: kvittens ("ER RAPPORT NR n
  MOTTAGEN"), följduppdrag ur innehållet (konvoj ⇒ "FÖLJ KONVOJEN", varefter nästa rapport väntas;
  jagare/bevakningsfartyg ⇒ "UNDVIK UPPTÄCKT", en gång per kontakt; jagade ⇒ "BRYT KONTAKTEN").
  Väntas en rapport (`Scenario.report_required`, eller ett telegram med flaggan `report_requested`,
  som kubas andra) och sambandstillfället stänger utan rapport: `SILENCE`, först "RAPPORT SAKNAS",
  sedan "BEKRÄFTA ATT NI ÄR OSKADDA". `received` sparar det vi rapporterat för en kampanj.
- **Slutrapportens samband** (R4): radion antecknar vid varje sänd rapport hur väl den stämde
  (`mission["report_truth"]`: eget läge mot sanningen, kontakternas läge framräknat till sändningen
  med rapporterad kurs och fart, kurs- och fartfel; sonarens beteckningar mot fartygen).
  `goals.report_summary` ⇒ `summary["radio"]` i `Game._end`; slutrapporten
  (`ui/widgets.radio_rows`) visar sambandstillfällen med rapport, största felet i rapporterat eget
  läge och kontakternas medianfel. Bara i slutrapporten: staben vet inget om felen.
- **Radiospaning** (R6, `avlyssna`): på antenndjup (masten fri, radion hel) avlyssnar radiomannen
  amerikansk trafik i `INTERCEPT_S` (60 s; avbryts om antennen går under). Sensor i radion:
  flygplan i luften inom 150 nm, jagare inom 60 nm, och om någon av dem haft datum de senaste 10 min
  ("jagarna rapporterar kontakt till varandra", larm). Kvalitet ur hur mycket som hördes: två
  sändare eller fler god, en osäker, ingen dålig. `InterceptHeard` ⇒ `Knowledge.intercept`. Vid
  tystnad på antenndjup föreslår radiomannen avlyssning högst var 30:e min (`idle_proposals`).
- **Kärnvapenrådet** (KV1–KV8, 2026-11-19; förebild B-59 den 27 okt 1962). Kärnladdningen (T-5) skjuts
  bara med tre nycklar: kaptenens, zampolitens och starpoms. Ersätter det villkorade tillståndet (R5).
  - **Ordern som kunskap** (KV1): `Scenario.nuclear_order` (forbidden, order_only, conditional, authorized) och
    `at_war`, och telegrammens flaggor `nuclear`/`war`, publiceras som `NuclearOrderRead` (radion: ordern vid
    start, telegrammen när de tas emot) ⇒ `Knowledge.nuclear_order()`, `at_war()`. Kuba, jagad, sundet och
    arktis: order_only ("vapen endast på order från Moskva"); jagads andra telegram: conditional; konvoj och
    duell: forbidden och krig; övningen: forbidden.
  - **Bombernas klassning** (KV2): sonaren hör bara den mottagna nivån (`TransientHeard.rl`, aldrig sanningens
    `practice`). Signalladdning 195 dB, skarp 230 dB vid källan, så en signalladdning nära låter som en skarp
    5–6 nm bort. Starkare än en signalladdning kan låta på 50 m (+4 dB) ⇒ skarp, säker; med plottets avstånd
    till jagaren (lösning ≥ osäker) det närmaste av de två, kvalitet ur hur mycket avståndets σ ger i dB
    (< 4/9/17 ⇒ säker/god/osäker); utan avstånd "troligen signal, eller skarpa långt bort", osäker. Maskin
    känner bomberna: skador ⇒ skarp, säker, skadat skrov; kraftig tryckvåg ⇒ skarp, säker; avlägsen ⇒ skarp,
    god, inte nära; små smällar ⇒ signal, god. Allt som `ChargeHeard` ⇒ `Knowledge.charges`. Kalibreringen
    oförändrad (`kontroll.py` kuba, kuba-kort, jagad, jagad-kort, konvoj-kort, konvoj-mot: som baslinjen).
  - **Krigsbedömningen** (KV3, `sim/war.py`, kunskap): ordern, krig, skarpt angrepp de senaste 30 min nära oss
    (för villkoret bara efter telegrammet) med den bästa bedömningens kvalitet, skadat skrov, och om staben kan
    nås (inte medan vi är jagade, angripna de senaste 10 min eller med en hotkontakt < 3 nm).
  - **Rösterna** (fasta regler, ingen slump): förbud ⇒ båda nej; tillstånd ⇒ båda ja. Zampoliten: ja med
    uppfyllt villkor eller utan order vid skarpt angrepp med minst god kvalitet. Starpom (Archipovs plats):
    villkoret bara med säker kvalitet; utan order bara om angreppet är säkert, staben avskuren och skrovet
    skadat (B-59-regeln); annars nej, och han föreslår `djup 150` eller `sänd kort rapport` (aldrig att skjuta).
  - **Rådet** (KV4, `stations/council.py`, `NuclearCouncil`, roll `Role.ZAMPOLIT`, Gromov, kapten 3:e rang):
    `kärnvapenråd` (även `förbered kärnladdningen`) kräver T-5 i en tub. Zampoliten och starpom svarar efter
    30 s med bedömningen och skälen; torpedrummet ger beskedet 10 s senare. Tre nycklar ⇒ skarp i 10 min
    (`ARM_S`). Samma läge hålls inte igen inom 5 min (`council.again`). Systemtavlans panel VAPEN visar
    "Kärnladdning: säkrad / rådet samlas / nycklar 3/3, skarp N min".
  - **Torpedrummet** (KV5): T-5 utan nycklar ⇒ "kärnladdningen kräver kärnvapenråd"; med nycklar frågar det
    en gång (`torp.nuclear_confirm`, larm) och skjuter på upprepad order, aldrig i salva; efter skottet är
    nycklarna tillbaka. `nuclear_authorized`/`nuclear_condition` i `World.mission` är borta.
  - **Slutet** (KV6): målet `NuclearFired` (alla scenarier, `Game` lägger till det, prövas först och slutar 30 s
    efter detonationen, före sänkt-målen) ger utfallet `nuclear`. Slutrapporten (`goals.council_summary`,
    `ui/widgets.council_rows`) visar varje råd: vad zampoliten och starpom sa, vad de trodde och sanningen
    (skarpa och signalladdningar inom 600 m den sista halvtimmen, `mission["charge_log"]`).
- **Starpom** (`stations/starpom.py`, `FirstOfficer`, `Role.XO`, Sokolov, kapten 3:e rang): `starpom har befälet`
  ⇒ kaptenen i hytten; starpom svarar på förslag via `Station.on_suggestion` (Game frågar stationerna efter
  leverans; sant = beslutat) och ger ordern med `game.command(order, by="starpom")` (`OrderIssued.by`, räknas
  inte i loggboken). Mandat `MANDATE` (orderklasser; aldrig avfyring, salva, sändning, ytläge, avbrott,
  aktiv sonar, radar, foto) plus det ordern lägger till (`ORDER_MANDATE` efter `Knowledge.order_tasks`, ur
  `Scenario.tasks`: patrull, rapport, anfall, foto, ut, station, övning; testat mot målen): anfall ⇒ `anfall S-x`.
  Han väger förslag mot ordern (`_objection`, fasta regler, inte vid larm eller jakt): nej (`xo.decline`) till
  styrorder från andra än navigatören medan navigatören anfaller eller följer, och djupare än radion behöver
  (`RadioStation.up_depth`: antenndjup eller flytkabelns 50 m) när ordern kräver rapport. Telefonorder (`phone_orders`, `_on_issued`: kaptenens order medan starpom har befälet, per sak
  `SLOTS` djup/kurs/fart/framdrivning) ändrar han inte själv på förslag de första 10 minuterna (`PHONE_ORDER_S`):
  telefonen ringer i stället (`phone_order`: "Sonar föreslår djup 150. Ni beordrade djup 50 klockan …"); larm och jakt går före. Med anfallsorder ropas kaptenen (fara) 2 min före
  navigatörens `attack_eta_t` och när ett klassat stort fartyg med färsk lösning ≥ osäker är < 3,5 nm
  (`_target_watch`); `nav.attack.arrived` är fara; radions förvarning ringer när ordern kräver rapport. Väckning (`_wake`): info = lampan (civil kontakt, `plot.maneuver`, ny kontakt),
  fråga = telefonen ringer (hotkontakt med lösning ≥ osäker, stort fartyg, konvoj, telegram, förslag utanför
  mandatet, tidsgränsen 15 min, `väck mig`, larm i `ALARM_LEVELS`; samma fråga högst var 10:e min; ordonnansen
  efter 20 s), fara = högtalaren (`alarm_level` "danger": övriga larm, jakttecken) ⇒ 1× och kaptenen är i centralen direkt
  (`_arrive`, samma tick som `jag har befälet`; ingen gång sedan 2026-11-19, telefonen tystnar) och får
  lägesrapport (`xo.handback`, `officer.situation`).
  En väckningstid som passerat innan överlämnandet släpps vid överlämnandet.
  `tid 30`/`60` bara med starpom i befäl; `sov` ⇒ 60×, och larm som bara tänder lampan (info/None i
  `ALARM_LEVELS`) sänker inte tiden (`keeps_time_scale`); frågor och fara sänker han själv i `_wake`. Status: `StatusSnapshot.command`, `captain_at` (central/cabin),
  `phone`, `sleeping` (via `Station.status_fields`). Vyn `hytt` (`ui/cabin.py`, `ui/cabin_render.py`: från 64 × 18 sedd från kudden i perspektiv,
  dörren längst bort till höger, `_Room`; på skottet rivkalendern för orderns dag
  (`StatusSnapshot.order_day` via starpom, nästa blad vid midnatt), fotot av hans första ubåt, diplomet,
  medaljerna och familjen så långt platsen räcker; under dem, när platsen räcker (minst 16 × 6), kortet på
  väggen (`_wall_chart`, ur `Game.chart()`: land, kust, besticket, vi och kontakternas tecken, utan text) och
  under repeatrarna krängningsmätaren (`_clinometer`, кренометр, ur `sway_of`); ljuset (`_shade` färgar om varje ruta: natt ⇒ bara
  nattlampan, telefonens sken gult/rött på skottet, rök dämpar), ögonlocken när han sover (`lids_of`, öppna när
  det ringer), andningen, taklampan och mössan svänger (`sway_of`: jagade, sjön nära ytan, krängning i gir),
  damm från rören när vi är jagade och dis av rök; dörren (`StatusSnapshot.door` ur starpom: `steps` fötter i
  ljusstrimman 4 s före ordonnansens knackning, `ajar` 12 s med honom i springan); mindre fönster den enkla bilden) öppnas
  av sig själv (`SubApp._follow_command`) och står först i Tab-ordningen; visar bara starpoms och telefonens
  rapporter (fyra rader), Enter svarar. Raden ovanför (`call_line`) blinkar RINGER medan telefonen ringer och visar
  sedan ERT BESLUT med förslaget starpom bad om (`StatusSnapshot.decision`, `FirstOfficer.asking`, så länge det är
  det väntande förslaget); `ja`/`nej` medan det ringer lyfter luren först (`intercept`), så ordonnansen kommer inte. Ljudet i hytten (`ambience.muffled`, `audio.from_central`): båten ×0,55, mumlet
  svagt, inga hydrofonljud eller sväv, centralens repliker dämpade genom skottet (`muffled_voice`; utan mixern
  tysta), starpom i telefonen (`phone_voice`), larm hörs; telefonen `phone`, knackning
  `knock`. 8 frön (`kalibrering/starpom.py`, kaptenen lämnar över igen efter 10 min lugn): inga order utanför
  mandatet, utfallen som ja-boten (kuba 8 patrol_end, konvoj 8 convoy_missed); kuba 3–12 ringningar och 0–2
  fara på 3,5 h, konvoj 6–20 och 0–4 på 1–3 h. Efter ordern i mandatet (2026-11-16; kaptenen går till centralen
  när starpom ber om hans beslut): kuba-kort rapporten i 5 (ja-boten 4; förut 0, ingen sände), med `salva`
  (kaptenen skjuter bara i centralen) konvoj 3 sänkt och 1 neutral (vaken salvakapten 3), konvoj-kort 1 (1);
  utan starpoms rop före skjutläget och vid stort fartyg < 3,5 nm var konvoj 0. Nej i 5 av 40 körningar (1–4 st).
- **Trim och flytkraft** (`sim/trim.py`, sanning; `TrimState` i `own.sys.trim`): båten är trimmad för
  startdjupet (`TrimState.start`). Vikten ändras av djupet (skrovet trycks ihop, `COMPRESS_T_PER_100M` 1 t),
  språngskiktet (under det bär kallare vatten `LAYER_LIFT_T` 3 t, över `LAYER_BAND_M`), smältvatten under isen
  (`MELT_T` 1 t ovanför 25 m), torpeder och skenmål (`TORPEDO_T` 2 t, ersättningstanken tar `REPLACE_SHARE`
  70 %, resten saknas förut) och läckvatten. Djuprodren bär `plane_capacity` = 0,8·v² ton (högst 10, gånger
  rodrens hälsa); det de inte bär (`free_t`) driver båten 0,03 m/s per ton när den håller djupet, och tar bort
  djupstyrningen helt vid `CONTROL_LOST_T` 2 t. Så länge styrningen orkar hålls djupet exakt (annars tror
  navigatören att vi byter djup). Barlasten bär och trimmen spelar ingen roll (`ballast_carries`): på väg upp
  till ytan (huvudbarlasten blåses, från 40 m) och vid en ny djuporder i högst 2 kn tills djupet är nått
  (lodrätt, t.ex. genom en öppning i isen). Utjämningstanken −25 … +15 t (läckgränsen `TRIM_RESERVE_T` är
  dess 25 t) pumpas 1 t/min, för–akter 0,5 t/min (±8 t); pumparna hörs (`PUMP_LEVEL` 121 dB, ~+1,7 dB på
  smygmotorn, inget bredvid turbinen). Lutningen 0,6° per ton framåtlast.
- **Back i maskin** (2026-11-19; sanning i `sim/ship.py` och `sim/ownship.py`, order hos navigatören):
  `back N`, `back`/`sakta back` (2 kn), `halv back` (halva backfarten), `full back`; `fart N` går framåt
  igen och `stopp` stoppar. `ShipState.speed` är alltid farten genom vattnet (≥ 0) och `astern` riktningen,
  så allt som läser farten som belopp (buller, rodrens last, skador) fungerar som förut; `track` är
  riktningen båten rör sig i (kursen + 180° akterut) och används av rörelsen, besticket, egna fartvektorn och
  navigatörens blick framåt (`chart_ahead`). Maskinen slår om via stopp: mot farten bromsar den
  `BRAKE_KN_PER_S` 0,15 kn/s (stopp 0,05), sedan accelererar den åt andra hållet (`reversing`, `prop_astern`).
  Backfart `max_astern_speed`: 8 kn på turbinen, 3 på smygmotorn, gånger framdrivningens hälsa. Akterut girar
  båten med en tredjedel (`ASTERN_TURN`) och djuprodren bär 30 % (`ASTERN_PLANES`), så djupet hålls mest med
  trimmen. Omkastning från ≥ 2 kn är en transient (`Transient("astern")`, `acoustics.astern_level` 120 +
  2,5·fart dB: 12 kn ≈ en torpedutskjutning) som jagare pejlar till ett datum (σ 0,3 nm) som en ping,
  amerikanska ubåten och hamnens hydrofoner hör som annat eget ljud. Propellern kaviterar akterut vid halva
  farten (`cavitation_speed(djup, astern)`), och maskin föreslår då `back N`. Navigatören säger "Omkastningen
  hörs långt" från ≥ 8 kn och publicerar `OwnSoundMade("astern")` (plottets blyertsmärke ◂, sonarvyns märke).
  Går vi akterut in i is eller botten tar propellern och akterrodren skadan (`hull_stop` = (t, akterut, vad)).
  Efter ett tvärstopp mot en isvägg, eller när vi står fast mot land, föreslår navigatören att gå loss åt
  andra hållet (`back 2` om fören tog i, `fart 2` om aktern) och efter 90 s back en kurs bort med fart 5
  (`nav.suggest.unstuck`, kursen med djupast vatten på kortet). Efter en grundstötning föreslås ingen back:
  båten lyfts från botten och kommer loss själv (med back gick ett frö i jagad förlorat);
  backar vi mot grunt vatten föreslår han stopp i stället för en gir (`nav.suggest.land_astern`). Fingeravtrycket
  är oförändrat så länge ingen backar. Tester: `tests/test_astern.py`.
- **Trimmaren** (`stations/trim.py`, `TrimStation`, `Role.TRIM`, Zajtsev, mitjman, vid trimposten i centralen,
  трюмный): bedömningen `est` ± σ ur det han vet (pumpat och skjutet exakt, läckan ±10 %, kompressionen,
  0,02 t²/m för okänt djupberoende, 0,0005 t²/s åldring) och rodret och driften var 10:e s (Kalman,
  σ = (0,2 + 0,03·rodrens last)·(1,6 − skicklighet)); kvalitet ur σ (0,4/0,8/1,6 t). Trimmar bort ≥ 1 t
  (0,3 t när vi ligger still) själv på turbinen; på smygmotorn ber han först (`trim.suggest`, `trimma`), men
  inte medan ett annat förslag väntar eller ligger i kön (det skulle ta dess plats); i fara (obalans > rodren
  + 2 t) pumpar han alltid och säger varför. Order: `trimma`, `trim stopp` (inga pumpar utom i fara),
  `trim` (rapport med kvalitet), `ligg still` (fart 0, kräver σ ≤ 0,6 och ≤ 1 t, annars ber han att få trimma;
  slutar vid order om fart). Starpom får besluta om alla fyra. Panelen TRIM (vikt ± σ, lutning,
  utjämningstank, pumpar), `TrimTanks` till genomskärningen (tankarna i I, III och IX med vattennivå) och
  `pitch`/`plane_load` till statusraden: centralens djuproder står ute med lasten (`PLANE_HOLD_DEG` 15° vid
  full last, tung ⇒ uppåt) och libellen visar lutningen (`PITCH_SPAN_DEG` 5°). Ett lutande skrov i
  genomskärningen provades men blev svårläst med rak text.
  Sjön suger (`_heave_advice`, V3 2026-11-19): trimmaren ser djupmätaren slå i takt med sjön
  (`OwnShip.heave_amp_m`, egna instrument) och räknar om utslaget till det beordrade djupet på väg upp
  (`heave_depth_f`). Blir marginalen mellan kölen och 13 m (`BROACH_DEPTH_M`, tornet i ytan) under 1 m föreslår
  han minsta fart upp till 7 kn som räcker (`heave_speed_f`), annars `djup 25` (`trim.heave`, larmförslag, god,
  spärr 10 min). Panelen TRIM visar "Sjön suger: djupet slår N m" från 0,5 m, varning när tornet är nära
  ytan. Bryter tornet ändå ytan larmar centralen (`broach`, via maskins larmkö).
