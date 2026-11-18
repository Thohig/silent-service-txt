# Radion, starpom och trimmaren

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

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
  `Station.intercept` stoppar hans order under tiden; telefonen tystnar när han går, och ett andra
  `jag har befälet` på vägen ger `xo.walking`) och får lägesrapport (`xo.handback`, `officer.situation`).
  En väckningstid som passerat innan överlämnandet släpps vid överlämnandet.
  `tid 30`/`60` bara med starpom i befäl; `sov` ⇒ 60×, och larm som bara tänder lampan (info/None i
  `ALARM_LEVELS`) sänker inte tiden (`keeps_time_scale`); frågor och fara sänker han själv i `_wake`. Status: `StatusSnapshot.command`, `captain_at`, `walk_s`,
  `phone`, `sleeping` (via `Station.status_fields`). Vyn `hytt` (`ui/cabin.py`, `ui/cabin_render.py`: från 64 × 18 sedd från kudden i perspektiv,
  dörren längst bort till höger, `_Room`; på skottet rivkalendern för orderns dag
  (`StatusSnapshot.order_day` via starpom, nästa blad vid midnatt), fotot av hans första ubåt, diplomet,
  medaljerna och familjen så långt platsen räcker; under dem, när platsen räcker (minst 16 × 6), kortet på
  väggen (`_wall_chart`, ur `Game.chart()`: land, kust, besticket, vi och kontakternas tecken, utan text) och
  under repeatrarna krängningsmätaren (`_clinometer`, кренометр, ur `sway_of`); ljuset (`_shade` färgar om varje ruta: natt ⇒ bara
  nattlampan, telefonens sken gult/rött på skottet, rök dämpar), ögonlocken när han sover (`lids_of`, öppna när
  det ringer), andningen, taklampan och mössan svänger (`sway_of`: jagade, sjön nära ytan, krängning i gir),
  damm från rören när vi är jagade och dis av rök; dörren (`StatusSnapshot.door` ur starpom: `steps` fötter i
  ljusstrimman 4 s före ordonnansens knackning, `ajar` 12 s med honom i springan, `open` de första 4 s när kaptenen
  går, sedan gången); mindre fönster den enkla bilden) öppnas
  av sig själv (`SubApp._follow_command`) och står först i Tab-ordningen; visar bara starpoms och telefonens
  rapporter, Enter svarar. Ljudet i hytten (`ambience.muffled`, `audio.from_central`): båten ×0,55, mumlet
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
