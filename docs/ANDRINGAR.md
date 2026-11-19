# K-114 – ändringslogg

Vad som ändrats, nyast först: vad det betyder i spel, var det bor i koden och vad kalibreringen
visade. Systemen i detalj står i `docs/system/`, siffrorna i `kalibrering/README.md`.

## 2026-11-19 – periskopets händelser, sjögångens verkan, vädret och siluetterna i braille

Byggt i ordningen P1–P2, V1–V4, V5, SB1–SB3. Tester i `tests/test_periscope_events.py`,
`tests/test_sea_effects.py`, `tests/test_weather.py` och `tests/test_silhouettes.py`. Detaljer i
`docs/system/utkik.md` (Periskopet, Periskopbilden) och `docs/system/hav.md` (Sjögången, Vädret).

- **P1–P2 Periskopet ser händelser** (`sim/stations/lookout.py`, delad med bryggan). Plask, vattenpelare och
  träffar i okularet, bara det som når över horisonten och vågtopparna (plask 5 m, pelare 25 m, träff 60 m):
  ögat 1,5 m upp ser ett plask på ~6 nm, en pelare på ~12. `off.periscope.column`/`hit`, okularet ritar
  dem, och utkiken (bryggan och periskopet) ger plottet blyertsmärken där det syntes (`EventSighted`).
- **V1–V4 Sjögångens verkan.** Havsbrus +2,5 dB per Beaufortsteg från 3, jagarens ping −3 dB per steg från
  5, sjöklotter mot masterna från 4 (flyget och jagaren), sjörök från 5, vågtopparna skymmer fartyg och
  plask, bedömningarnas σ +10 % per steg över 3. Grov sjö är alltså dålig för båda sidor.
  Sjön suger båten mot ytan nära ytan från 4: i låg fart på periskopdjup i Beaufort 5 bryter tornet ytan
  och syns 15 s som en ubåt i ytläge. Trimmaren ser djupmätaren slå och föreslår fart eller djup innan
  (larmförslag); periskopet sköljs över en del av tiden. Konvojen går i Beaufort 5.
- **V5 Vädret** (`sim/weather.py`). Sjögången ändras ett steg i taget, högst var 30–60:e minut, mot
  prognosen i ordern (`VÄDER:`): kuba 3 → 4, konvoj 5 (4–6). Egen slumpström. Bryggan, periskopet och
  sonaren (havsbruset) säger till när sjön ändrats.
- **SB1–SB3 Siluetterna i braille** (`ui/silhouettes.py`). Profiler i meter med samma höjder som utkiken
  räknar med, projicerade efter vinkeln på bogen, skurna av horisonten och vågorna, i verklig vinkelstorlek
  men med minsta masthöjd 8 prickar (låg, bryggan) och 20 (hög, kikaren); i verklig skala vore en jagare på
  2 nm nästan osynlig i låg. Bogvåg efter farten, rök ur ångarna, vattenpelaren som stiger och faller.
  ASCII-siluetterna borta.
- **Kalibreringen** (`kontroll.py`, 8 frön): allt som baslinjen utom konvojerna (Beaufort 5): konvoj ja
  missar efter 149 min mot 112, konvoj-mot passiv anfallen 4 ⇒ 2. Baslinjen sparad för konvojerna.
  `konvoj_salva.py konvoj-kort`: 1 sänkt av 8 (förut 0–2).

## 2026-11-19 – back i maskin (B1–B4)

Tester i `tests/test_astern.py`. Detaljer i `docs/system/besattning.md` (Back i maskin).

- **B1 Order och rörelse** (`sim/ship.py`, `sim/ownship.py`, navigatören). `back N`, `back`/`sakta back`,
  `halv back`, `full back`. `ShipState.astern` med farten som belopp; maskinen slår om via stopp och bromsar
  0,15 kn/s, backfart 8/3 kn, gir ⅓ och djuproder 30 % akterut. Besticket och fartvektorn följer `track`.
  Ryska: Malyj/Srednij/Polnyj nazad.
- **B2 Ljud.** Omkastningen är en transient (120 + 2,5·fart dB) som jagaren pejlar; propellern kaviterar
  akterut vid halva farten och maskin föreslår `back N`; plottet och sonarn märker omkastningen.
- **B3 Vyer.** Huvudraden, systemtavlan, ubåtsvyn, hytten och överlämnandet säger back; centralens logg
  visar B och telegrafen har läget B.
- **B4 Kollisioner och förslag.** Akterut tar propellern och akterrodren skadan; navigatören föreslår att
  gå loss åt andra hållet efter ett tvärstopp mot is eller när vi står fast mot land, sedan en kurs bort
  i 5 kn, och stopp när vi backar mot grunt vatten. Inte efter en grundstötning (båten kommer loss själv;
  med back där gick jagad frö 2 förlorat). Fingeravtrycket (30 min, 2 frön, alla scenarier) oförändrat mot före ändringen.

## 2026-11-19 – radion (R1–R6)

Byggd i ordningen R1+R2, R3, R4, R6, R5. Tester i `tests/test_dispatch.py`,
`tests/test_headquarters.py` och `tests/test_nuclear_condition.py`. Detaljer i
`docs/system/besattning.md`.

- **R1 Rapporten har innehåll** (`sim/dispatch.py`, kunskap). `sänd rapport` (allt),
  `sänd kort rapport` (eget läge och det som hänt), `sänd rapport S-3` (en kontakt). Radiomannen
  sätter ihop rapporten ur kunskapen: bestick med σ, kontakter med lösning ≥ osäker (hot först, högst
  fem), konvojens baskurs och det som hänt sedan förra rapporten (spaningsfoto, hörd torpedträff,
  jagade). Längden i femsiffergrupper ger sändningstiden i morse: 6 s + 4 s per grupp (kort rapport
  ~22 s, två kontakter ~46 s; förut alltid 30 s). Radiomannen säger tid och pejlrisk och föreslår
  kort rapport när hela vore stor risk. Det sända står som remsan ДОНЕСЕНИЕ i loggen
  (`ui/strips.py`, kind "outgoing") och publiceras som `ReportTransmitted`.
- **R2 Pejlningen beror på längden** (`sim/enemy.py`, `DF_*`; `Emission.duration`). Kortvågen sänds
  ut med sin längd när sändningen slutar eller avbryts. Under 10 s pejlas den aldrig, över 25 s
  alltid, däremellan linjärt; datumets σ = 1,5 nm · √(30 s / längd), 0,7–3 nm (förut alltid 1,5 nm).
- **R3 Huvudstaben** (`sim/headquarters.py`, kunskap, ägs av radion). Vet bara vad vi sänt. Svarar
  vid nästa sambandstillfälle, högst tre telegram: kvittens, följduppdrag ur innehållet (konvoj ⇒
  "FÖLJ KONVOJEN", jagare ⇒ "UNDVIK UPPTÄCKT", jagade ⇒ "BRYT KONTAKTEN") och upptrappning när en
  väntad rapport uteblir ("RAPPORT SAKNAS", sedan "BEKRÄFTA ATT NI ÄR OSKADDA"). En rapport väntas
  när ordern kräver det eller ett telegram ber om det (kubas andra, flaggan `report_requested`).
  Det rapporterade sparas (`received`) för en framtida kampanj.
- **R4 Sambandet i slutrapporten** (`goals.report_summary`, `ui/widgets.radio_rows`). Radion
  antecknar sanningen bakom varje rapport (`mission["report_truth"]`). Slutrapporten visar
  sambandstillfällen med rapport, största felet i rapporterat eget läge och kontakternas medianfel i
  läge och kurs. Staben vet aldrig felen.
- **R6 Radiospaning** (`avlyssna`). På antenndjup avlyssnar radiomannen amerikansk trafik i en
  minut: flygradio inom 150 nm, örlogsfartygens radiotelefoni inom 60 nm och om jagarna rapporterar
  kontakt till varandra (larm). Kvalitet ur hur mycket som hördes. `InterceptHeard` ⇒
  `Knowledge.intercept`. Vid tystnad på antenndjup föreslår han avlyssning högst var 30:e minut.
- **R5 Villkorat tillstånd för T-5.** Ett telegram kan ge tillstånd på villkor (flaggan
  `nuclear_condition`): i jagad bara om vi angrips med skarpa sjunkbomber efter telegrammet;
  signalbomber räknas inte (`mission["real_charges"]`). Uppfyllt frågar torpedrummet en gång och
  skjuter på upprepad order inom en minut; aldrig i salva, och avfyring föreslås som förut aldrig
  som ja-order. Zampolitens samtycke är inte byggt (se `docs/IDEER.md`).

Kalibrering efter R1–R6 (8 frön, ny `baslinje.json`): kuba-kort ja rapporterat 2 ⇒ 3 (kortare
sändningar pejlas mer sällan); arktis ja tid till stationen 295 ⇒ 336 min (median, se isekolodet
nedan). Inget annat flyttat. Ryska talet rent över alla scenarier.

## 2026-11-18 (kväll) – fem fel från provspelet

Utredda (orsak och återskapning i commit-meddelandena) och rättade. Detaljer i `docs/system/hav.md`.

- **Pingar "för första gången" igen** (`stations/sonar_room.py`). När sonar tappat en jagare som
  kontakt blev nästa ping en ny okänd pingare ("Någon söker"). Nu matchas en ping utan beteckning
  också mot kända pingare inom bäringsgrinden som pingat de senaste 15 min (`PING_KNOWN_S`).
- **Båten fast mot stranden** (`seabed.bottom_contact`). En gir svängde in aktern i land, och varje
  steg ställdes tillbaka, även de som ledde bort från land: båten stod 18 min med fart på loggen och
  besticket gled 0,35 nm. Nu får ett steg som inte gör kontakten värre gälla (gör giren det värre
  gäller förflyttningen med förra kursen). Trycker båten mot land står den still (loggen 0) och
  maskin säger `bottom.pressed` var 2:a minut; `bottom.touch` högst en gång per minut.
- **Ytläge med fören eller aktern under is** (`navigation/ice.py`). Båten gled till öppningens bortre
  ände, och navigatören prövade bara isen ovanför tornet. Nu lodar isekolodet också för och akter
  (`hull_clear`); ytläge föreslås bara när hela skrovet har is vi kan bryta, annars lägger
  navigatören om mot mitten (`nav.vak.reposition`, högst två gånger). Periskopdjup kräver bara
  tornet. arktis-kort (48 körningar): stötar efter ytläge 7 ⇒ 3, "tjock is" efter ytläge 7 ⇒ 1,
  stationen nådd 17 ⇒ 13 (omläggningarna tar tid).
- **Kurs mot land** (`navigation/bottom.py`, `stations/plot.py`). Kortets strand ligger upp till
  0,3 nm fel; stod besticket på kortets land fast vi flöt visade alla kurser land, och navigatören
  tiger. Nu föreslår han kursen mot närmaste vatten på kortet (`nav.suggest.chart_land`, larm), och
  plottets ben prövas mot kortet (`course_safe`): annars giren åt andra hållet, annars inget förslag.
- **Fingeravtrycket** (`kalibrering/fingeravtryck.py`): filnamnet efter `--spara`/`--jämför` räknades
  som minuter; flaggorna kan nu stå var som helst.

Kalibrering: jagad ja undkommit 4 ⇒ 6.

## 2026-11-18 – förslagen och talet

- **Ryskt tal för alla repliker.** 76 typer saknade rysk fras och lästes som "товарищ командир,
  …"; nu har alla som läses upp en. Det som aldrig läses upp står i `phrases.NO_SPEECH`, och testet
  kräver rysk fras för allt annat (förut 80 %). Svensk fritext i data läses inte på ryska: skälet
  bär en nyckel (`why`) eller sägs allmänt ("Выполнить не могу"). T-5 läses "Т 5".
- **Larmförslag står 30 s** (`Game.held`, `ALARM_HOLD_S`). Ett vanligt förslag tog förut ett
  väntande larms plats (t.ex. "sänd rapport" över "flygradar nära – djup 60"). Nu väntar det tills
  larmet är besvarat eller stått 30 s (det nyaste vinner) och släpps om det blivit äldre än 60 s,
  redan är beslutat eller någon station säger nej. Mastorder (sända, periskop, radar, foto) föreslås
  inte när det beordrade djupet är under periskopdjup (`Station.MAST_ORDERS`). 45 korta spel:
  larmförslag ersatta av rutin 7 ⇒ 0. kuba-kort ja rapporterat 3 ⇒ 2 (boten lyder nu flyglarmet).
- **Radion efter flyget** (`AirRadarHeard`, `Knowledge.air_close_t`). Radarvarnarens svep ger
  kunskap om flygradarn. Radion föreslår inte att sända medan den hörs nära, och föreslår
  periskopdjup igen när flyget varit tyst i två minuter och minst 2½ min av fönstret är kvar.
  Vakthavande föreslår djup 60 så länge flygradarn är nära (förut bara när styrkan ändrades).
