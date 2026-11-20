# K-114 – ändringslogg

Vad som ändrats, nyast först: vad det betyder i spel, var det bor i koden och vad kalibreringen
visade. Systemen i detalj står i `docs/system/`, siffrorna i `kalibrering/README.md`.

## 2026-11-20 – statusraden ur stationerna

Ingen ändring i spel (fingeravtrycket lika, 20 min, 2 frön, alla scenarier). `Game.status()` hämtade
sonarns kontakter och brus och periskopets läge direkt ur `SonarRoom` och `PeriscopeWatch`; nu lämnar
stationerna dem själva i `status_fields()`, så att `Game` inte känner någon enskild station i
statusbilden. Kontakternas ordning (hot först, `S-2` före `S-10`) bor i `sonar_view.held_by_kind` och
`designation_order`.

## 2026-11-19 – förslagen i hytten syns

När starpom ringde om ett förslag utanför mandatet var det svårt att se vad man skulle ta ställning till:
hyttens rapportrad hade två rader, och samtalet (ofta ett larm och förslaget i samma mening) klipptes så att
förslaget, som kommer sist, inte syntes. `ja` medan det ringde verkställde förslaget men lät telefonen ringa,
så ordonnansen knackade ändå. Nu har hytten en egen rad ovanför rapporterna (`ui/cabin_render.call_line`):
RINGER blinkar medan telefonen ringer, och när kaptenen svarat står ERT BESLUT med vem som föreslår vad och
ja/nej tills det är besvarat eller inaktuellt (`StatusSnapshot.decision` ur `FirstOfficer.asking`).
Rapportraden är fyra rader. `ja`/`nej` medan det ringer lyfter luren först (`FirstOfficer.intercept`).

## 2026-11-19 – land på hela nattsikten

Landets kontur syntes på natten bara på halva sikten (`NIGHT_LAND = 0.5`), alltså ~1,25 nm. I Clyde, som
spelas helt i mörker, såg periskopet och bryggan därför nästan aldrig land utom tätt intill stränderna i
sunden. Nu syns landet ut till hela sikten även på natten (2,5 nm, längre i månsken), i både periskopet
(`PeriscopeWatch._observe_land`) och på bryggan (`BridgeWatch._land`); konstanten är borta.
Navigatörens fixar påverkas inte (fyrarna, inte landet).

## 2026-11-19 – sparsammare CI

GitHub Actions-minuterna tog slut: `--slow` (10–20 min) kördes vid varje push på alla grenar, även för
ändringar i `.md`. Nu (`.github/workflows/tester.yml`): push bara till `main` och då bara de snabba testerna,
`--slow` vid pull request och manuellt (`workflow_dispatch`), `paths-ignore` för `**.md` och `docs/**`,
`timeout-minutes` 30. Lokalt: `uv run pytest -q` före varje commit, `--slow` före större steg (CLAUDE.md).
Kalibreringsbaslinjen sparad om med clyde och clyde-in (`kontroll.py`, `MAX_H` 10 h).

## 2026-11-19 – «Клайд»: Firth of Clyde (N2–N6)

Nytt scenario `clyde` och kort variant `clyde-in` (menyn efter sundet). Natten till 20 oktober 1962: in
förbi Pladda, spela in en Polarisubåt som går ut från Holy Loch, ut söder om Pladda före gryningen.
- **N2 molnen** (`environment.Clouds`, `Environment.clouds`, `Light.cloud`): täcket släcker månljuset och
  stänger stjärn- och månfixen från 0,6 ("molnen täcker himlen"); uppklarningar 10–25 min.
- **N3 fyrarna** (`seabed.Lighthouse`, `light_visible`, `Scenario.light_list` ⇒ `Knowledge.lights`,
  `navigation/fixes.py` `_start_light_fix`, `lights_expected`): med fyrlista ger natten fix bara på fyrar som
  syns (lysvidd, land emellan): två σ 0,1, en σ 0,2, ingen ingen. Navigatören föreslår periskopfix på natten
  bara när kortet säger att en fyr borde synas. Fyrarna står på sjökortet (✶).
- **N4 geografin** (`seabed.Firth`, `clyde_seabed`): bassänger med branta väggar, Arran och Cumbraeöarna
  som ellipser, Holy Loch som vik; kortet med 0,1 nm fel. Bottnen räknas i ett rutnät (0,05 nm) en gång,
  annars tog den 3/4 av tiden per tick (7 ⇒ 2 ms).
- **N5 motståndet och målen** (`sim/clyde.py`, `scenario/clyde.py`, `goals.RecordGoal`,
  `stations/recording.py`): Polarisbåten (`TransitAI`, ~150 dB i ytläge i 10 kn) går ut 00:30 ± 30 min;
  sonarrummets bandspelare spelar in den (10 min med SE ≥ 8 dB, bara med ordern `inspelning`) och föreslår
  djup 40 eller kurs mot den; inspelningen ⇒ `RecordingMade` ⇒ `Knowledge.recorded`. Hydrofonlinje och
  patrullbåt i västra rännan, en patrullbåt vid Toward–Dunoon (lyssnar i fred, pingar när de söker,
  `DestroyerAI.quiet_patrol`); Largs-rännan obevakad. Fiskebåtar (`FishingAI`), handelsfartyg och färjan
  (`ClydeTraffic`). Ingen minering (fred). Under inspelningsordern föreslår varken navigatören botten eller
  sonar skiktet om vi inte är jagade.
- **N6 kort variant** `clyde-in`: 01:20, söder om Little Cumbrae 1,9–2,6 nm från farleden, besticket σ 1,0
  (`Scenario.start_fix_sigma`), Polarisbåten 3–4 nm bort, tidvattnet vänder; 40 min.
- **Kalibrering:** se `kalibrering/README.md` (Clyde). Tester i `tests/test_clyde.py`.

## 2026-11-19 – jagarkaptener med temperament (J1–J2)

Jagarna jagar olika: en metodisk kapten som förut, en envis som söker saktare och längre (håller ett
gammalt datum en halvtimme) och en ivrig som stänger i 27 knop, söker i 16 (hör sämre, hörs mer), går in
på ett osäkrare datum och ger upp tidigare. Temperamentet dras ur en egen ström så att jagarens övriga
slump står still; hamnens patrullbåtar är alla metodiska. Spelaren får veta det bara genom plottet: efter
tio minuters jakt "Om jagaren S-1: han pingar tätt, var 8:e sekund" (och farten när lösningen räcker), efter
25 minuter "Han har jagat oss i 25 minuter och ger inte upp." `enemy.py` (`Temperament`, `TEMPERAMENTS`,
`draw_temperament`), `stations/plot.py` (`_hunter_watch`, `hunter_data`); tester i `tests/test_temperament.py`.
Provkörning (ja-boten, jagad-kort/kuba-kort/konvoj-kort, 8 frön): plottet säger pingtakten i de flesta
jakter; farten aldrig (lösningen på en jagare som jagar oss är dålig).

## 2026-11-19 – tystnad i båten och skrovknak (H1)

**Tystnad i båten:** när plottet tror att vi är jagade och vi smyger (smygmotorn eller högst 6 kn, under
ytan) säger vakthavande "Tystnad i båten …", och sedan talar besättningen lågt: loggboken skriver
rapporterna kursivt grått och talet blir lägre och dovare (effekten `hushed`). Larm ropas som förut.
Tystnaden hävs när det varit lugnt eller fort i en minut. Ingen order. `stations/officer.py`
(`_hush_watch`, `_hush_filter` i `ReportQueue.filters`), `ui/audio.py` (`hushed_voice`), `ui/widgets.py`.

**Skrovknak:** en djupändring fortare än 1 m/s under 80 m (rodren i ungefär 6 kn och uppåt) knakar var
25:e meter, en transient på 132 dB som jagaren kan höra rakt ovanför. Under jakt säger maskin det, högst
var tredje minut: "Skrovet knakar när vi går ned, kapten. Det hörs i vattnet. Långsammare djupändring, i
låg fart, knakar inte." `ownship.py` (`_groan_step`), `stations/engineering.py`. Tester i
`tests/test_hush.py`.

## 2026-11-19 – nedräkning för torped i vattnet (T1)

När bäringen till en fientlig torped står still säger sonar hur länge det är kvar: "Torpeden bäring 045.
Bäringen står still, den kommer mot oss! Framme om cirka 1 minut 20." Tiden räknas ur hur fort ljudet
växer (nivån stiger 8,7 dB per gång avståndet halveras … τ = 8,7 / lutningen), med kvalitet ur
spridningen i avläsningarna och ett modellfel på 20 %. Under 90 s ropas den var 10:e sekund; längre än 4
minuter sägs ingen tid. `stations/incoming.py` (`eta_estimate`), `sonar.py` (`IncomingTorpedo.level`);
tester i `tests/test_torpedo_countdown.py`. Mot sanningen: god inom 30 % eller 10 s i 83–92 % av fallen.

## 2026-11-19 – omladdningen hörs (O1)

En omladdning slamrar två gånger: när torpeden körs in i tuben (30 s efter ordern) och när bakluckan
stängs. Slammret är en transient på 145 dB som jagaren hör och tar som datum, som omkastningen
(`enemy.py`). På smygmotorn eller när vi är jagade laddar minören försiktigt utan order: åtta minuter i
stället för fem och 12 dB svagare ("Vi tar det försiktigt, åtta minuter. Det slamrar ändå när torpeden går
in."). Under jakt föreslår han inte omladdning självmant. Plottet och sonarvyn märker slammret som ett
eget ljud (¤). `stations/torpedo_room.py` (`_clank`, `_load_quietly`, `RELOAD_QUIET_S`),
`acoustics.RELOAD_LEVEL`; tester i `tests/test_reload_noise.py`. Kalibrering: med jagaren i 5 kn hörs
slammret på 1 nm över skiktet men inte på 2 nm under; det försiktiga hörs inte på 1 nm.

## 2026-11-19 – starpom respekterar telefonorder (S1)

En order kaptenen ger per telefon medan starpom har befälet ändrar starpom inte själv på ett förslag de
första tio minuterna: han ringer i stället ("Sonar föreslår djup 150. Ni beordrade djup 50 klockan
03:12. Det beslutet är ert."). Larm och jakttecken går före som förut, och förslag om något annat
(kurs när kaptenen beordrade djup) beslutar han själv. Order som gavs i centralen före överlämnandet
räknas inte. `stations/starpom.py` (`phone_orders`, `SLOTS`, `_against_phone_order`, `PHONE_ORDER_S`);
tester i `tests/test_starpom.py`.

## 2026-11-19 – färre order

Hjälpen och ordlistan i menyn har färre order; de gamla formerna finns kvar som tysta synonymer
(`CommandSpec` utan hjälptext). Tester i `tests/test_simple_orders.py`.

- **`S-1`** (bara beteckningen, `AskContact` i `sim/orders.py`): plottets lösning och solfjädern;
  torpedrummet lägger till skjutlösningen när en tub är laddad och plottet har en lösning ≥ osäker (inte
  civila). Ersätter `läge S-1`, `plot S-1` och `skjutlösning S-1` i hjälpen.
- **`fix` väljer** (`_start_any_fix`): på periskopdjup eller i ytläge som förut (landmärken om land syns);
  djupt nere fix mot botten när kortet har djup och botten är brant (`_bfix_possible`), annars ber
  navigatören om periskopdjup. `stjärnfix` och `bottenfix` står inte i hjälpen; stjärnfixen föreslår
  navigatören själv.
- **`eld S-1`** (`FireAt`, `_pick_tube`): torpedrummet väljer den laddade tub som når, målsökande före raka
  före övning, aldrig kärnladdningen (den kräver tubens nummer). Bekräftelsen för icke-örlogsfartyg och
  varningen för neutrala i banan gäller som förut.
- **`torped`** visar tuberna och, om några går, torpederna i vattnet (ersätter `tuber` och `torpeder`).
- **`läget`** (vakthavande, `off.situation`): djup, kurs, fart, kontakter och besticket. `lägesrapport` när
  kaptenen själv har befälet ger samma sak i stället för att starpom vägrar.
- **Periskopet:** bara `periskop` och `periskop S-3`/`047` i hjälpen; upp, ned, vrid och förstoring med
  tangenterna i periskopbilden. **Back:** `back 3`; telegrafens ord är synonymer. **Småsaker:** `ljud`
  växlar, `radio moskva` i stället för `lyssna radio`, `sänd rapport S-3` och `förslag sonar` ur hjälpen.
- **Kalibrering:** `kontroll.py` som baslinjen (besättningens förslag om `fix` ges på periskopdjup och går samma väg som förut).

## 2026-11-19 – långvågen och sambandsschemat (L1–L4)

Telegrammen kan tas emot på djupet. Tester i `tests/test_radio_vlf.py`, detaljer i
`docs/system/besattning.md` (Sambandstillfällena och långvågen).

- **L1 Schemat:** ett missat sambandstillfälle säger när staben sänder om (nästa tillfälle); efter det
  sista når det oss inte.
- **L2 Flytkabeln:** på långvåg tar radion emot på ≤ 50 m och ≤ 5 kn på fem minuter (masten på antenndjup
  fortfarande en minut). Radiomannen sköter kabeln, föreslår djup 40 och fart 3 (antenndjup när vi går fort
  eller ordern kräver rapport), och säger till när farten drar kabeln under. Ingen kabel under is. Ingen ny
  order.
- **L3 Kvaliteten:** hel eller stympad ur mörker, fart ≤ 3 kn och djup ≤ 40 m (två av tre). Stympat visas
  som remsa med oläsbara grupper; radion föreslår djup och fart och lyssnar vidare.
- **L4 Vyerna:** djupprofilen visar flytkabelns djup och kabeln när den är ute, systemtavlan kabelns tid
  kvar, loggen "på långvåg".
- **Kalibrering:** `kontroll.py` som baslinjen utom jagad ja: escaped 6 ⇒ 5, lost 2 ⇒ 3 (frö 2: förvarningen
  under jakten gav en annan förslagsföljd; ±1); `baslinje.json` sparad efter långvågen. `kalibrering/langvag.py` (ja-boten, 8 frön): kuba tar nu emot
  på långvåg (9 radiogram, 4 stympade, förut 10 med masten), sundet 8 med masten och 2 på långvåg (förut 8),
  arktis och duell oförändrade (is respektive masten). Konvoj 1 mot 3: andra förslag tar båten djupare
  under fönstret; utfallen lika.

## 2026-11-19 – kaptenen är i centralen direkt

`jag har befälet`, högtalarens rop vid fara och starpoms rop före skjutläget ger kaptenen befälet och
lägesrapporten i samma tick. De 40 sekunderna i gången utan order (`WALK_S`, `captain_at == "walking"`,
`xo.walking`, `Starpom.intercept` för gången) är borta, liksom hyttvyns bild av gången och dörrens läge
`open`. Ropet före skjutläget kommer 2 min före (förut 2 min + gångtiden): kaptenen står i centralen lika
tidigt som förut. Kod i `sim/stations/starpom.py` och `ui/cabin_render.py`, tester i `tests/test_starpom.py`.
`kalibrering/starpom.py` (8 frön): utfallen som ja-boten (kuba 8 patrol_end, konvoj 8 convoy_missed);
kuba 2–10 ringningar och 0–2 fara, konvoj 1–9 och 1–4. Med `salva`: konvoj 0 sänkt (förut 1), konvoj-kort
1 anfallen och 1 neutral sänkt (förut 0 och 1), inom ±1.

## 2026-11-19 – kärnvapenbeslutet (KV1–KV8)

Förebild B-59 den 27 oktober 1962. Tester i `tests/test_war_council.py` och `tests/test_nuclear_keys.py`.
Detaljer i `docs/system/besattning.md` (Kärnvapenrådet).

- **KV1 Ordern som kunskap.** Vad ordern och telegrammen säger om kärnladdningen (förbjuden, bara på order
  från Moskva, villkorad, tillåten) och om kriget läses in som kunskap (`NuclearOrderRead`).
- **KV2 Bomberna klassas ur datan.** Sonaren vet inte längre om en sjunkbomb är skarp: den hör bara hur
  starkt det smäller. En signalladdning nära låter som en skarp långt bort; med plottets avstånd till
  jagaren blir det ett omdöme med kvalitet. Maskin känner skador och tryckvågor. Kalibreringen oförändrad.
- **KV3 Krigsbedömningen** (`sim/war.py`): skarpt angrepp med kvalitet, skadat skrov, om staben kan nås.
- **KV4 Zampoliten och rådet** (`stations/council.py`): `kärnvapenråd`. Zampoliten (Gromov) och starpom röstar
  efter fasta regler; tre nycklar ger en skarp kärnladdning i tio minuter. Starpom föreslår att gå undan.
- **KV5 Torpedrummet** kräver nycklarna; det villkorade tillståndet (R5) är ersatt.
- **KV6 Slutet:** en detonerad kärnladdning avslutar spelet (`nuclear`); slutrapporten visar vad rådet trodde
  mot sanningen.
- **KV7 B-59-regeln:** utan order från Moskva säger starpom ja bara om angreppet är säkert, staben avskuren
  och skrovet skadat.
- **KV8 Hök-boten** (`kalibrering/rad.py`): kuba inga nycklar (zampoliten ja 3 av 23 på signalladdningar som
  togs för skarpa, starpom aldrig); jagad nycklar 9 av 22, kärnladdningen skjuten i 4 av 8; jagad-kort inga.

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
