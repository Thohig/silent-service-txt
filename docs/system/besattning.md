# Radion och starpom

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
