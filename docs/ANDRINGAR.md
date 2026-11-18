# K-114 – ändringslogg

Vad som ändrats, nyast först: vad det betyder i spel, var det bor i koden och vad kalibreringen
visade. Systemen i detalj står i `docs/system/`, siffrorna i `kalibrering/README.md`.

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
