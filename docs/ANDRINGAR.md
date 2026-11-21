# K-114 – ändringslogg

Vad som ändrats, nyast först: vad det betyder i spel, var det bor i koden och vad kalibreringen
visade. Systemen i detalj står i `docs/system/`, siffrorna i `kalibrering/README.md`.

## 2026-11-21 – rättelser efter provspelet

Ett provspel (~100 spel i alla scenarier: provspelsboten, en kaosbot med udda order, riktade lägen och
krigspatrullen i 14 h, gränssnittet i 80×24, 120×40 och 220×60) gav inga undantag men felen nedan.
- **Loggen i smala fönster:** `ReportLog` ärvde `RichLog`s minsta bredd 78, så i fönster upp till
  ~100 kolumner bröts raderna vid 77 tecken i en 54–64 tecken bred panel och ord försvann. Nu
  `min_width` 20 (`ui/widgets.py`).
- **Telegrammen i nummerordning:** `ReportQueue` lägger ett telegram aldrig före ett tidigare
  (radiogram 8 kom före 7 i krig frö 7).
- **`kurs mot banken`:** navigatören styr mot närmaste vatten där hans sjökort visar 60–250 m botten
  (att lägga sig på) i scenarier med en bank (kuba, jagad); står vi redan där säger han det
  (`navigation/steering.py`, `BANK_*`). Utan känd plats slutar svaret inte längre med ett mellanslag.
- **Minustecken:** `kurs -10`, `fart -3`, `djup -5` ger en förklaring i stället för "Kapten?".
- **Starpom:** citerar kaptenens order med tresiffrig kurs ("kurs 000", inte "kurs 0"), och när
  högtalaren kallat kaptenen står det larmet först i överlämnandet (förut ett senare plottlarm).
- **Sjunkna kontakter:** sonar skickar `ContactSunk` när den hör brytningsljud från en känd kontakt.
  Kunskapen märker spåret (`ContactTrack.sunk_t`, inte längre hållet eller ett hot), sonar glömmer
  dess pingar (förut fick en annan jagare i nästan samma bäring den sänktas namn: "Pingtakten från
  S-3 har minskat" fem minuter efter att S-3 sjönk) och säger inte "Har tappat S-3", torpedrummet
  säger "S-3 har redan sjunkit" i stället för "Tid för torpeden mot S-3", och sjökortet ritar × där
  plottet trodde att den sjönk.
- **Staben i krig och efter hemkallelsen:** `Headquarters.read_order` läser scenariots och
  krigsskådeplatsens telegram före svaren. I krig inget "FÖLJ KONVOJEN" eller "ANGRIP EJ UTAN ORDER";
  hemkallade bara kvittensen. Svaren kommer före de nya orderna (krig frö 7 fick förut "PATRULLEN ÄR
  SLUT" följt av "FÖLJ KONVOJEN" och "ANGRIP EJ UTAN ORDER" vid samma tillfälle).
- **Djupt och fort utan pendling:** maskins sprint (`EngineeringStation._sprint`) godtar ett beordrat
  djup från 180 m ned till 290 m (eller djupgränsen) och räknar farten där; förut föreslog den "djup 220"
  var tionde minut när sonars undanmanöver tagit oss till 280, och ja-boten pendlade 220 ↔ 280 i över en
  timme med skrovknak varje gång (kuba frö 29: 3 knak i stället för ett tiotal). Sonars undanmanöver
  går uppåt bara till skiktet + 60 m. Smygmotor föreslås först 10 min efter senaste jakttecknet
  (`CREEP_AFTER_HUNT_S`; förut turbin och 36 s senare smygmotor).
- **Sonars djupförslag** börjar med "Kapten, sonar." och säger "laddningarna" bara efter sjunkbomber,
  annars "så att de tappar ekot".
- **Glesare under långa jakter:** undervattenstelefonen (2, 4, 8 … högst 30 min emellan, "De sänder
  fortfarande" efter första gången; kuba frö 29 10 rader i stället för ~50), "pingarna är mycket
  starka" per pingare på samma sätt, skenmål högst var 20:e minut (`DECOY_SUGGEST_S`) och med antalet
  kvar när två eller färre återstår.
- **En nära pingare** (≥ `PING_NEAR_RL`) får svänga 1,5°/s i bäring, högst 60°, och är ändå samma
  pingare (sundet: en patrullbåt förbi oss gav "Aktiv sonar … Någon söker" 9 gånger på 3 min).
- **Prov:** `tests/test_playtest_fixes.py`.

## 2026-11-21 – trådstyrd torped (53-62T, försök)

En trådstyrd försökstorped. Trådstyrda torpeder fanns inte i sovjetisk tjänst 1962 (de kom i slutet
av 60-talet), så den är ett försöksexemplar: två i förråd i alla scenarier utom övningen, inte
laddade från början (`ladda tub 7 tråd`).
- **I spel:** `eld S-1` väljer den före SET-53 om den är laddad. Eldledningen styr den var 20:e s mot
  plottets lösning, räknat från torpedens beräknade läge (skottpunkten och styrordern, inte
  sanningens läge). Styrorder på 10° eller mer sägs. När torpeden enligt räkningen är 0,6 nm från
  målet kapas tråden och målsökaren tar över. Fram till dess söker den inte, så andra fartyg på vägen
  drar den inte till sig. Utan lösning går den vidare på sin kurs och torpedrummet säger det. Skjuten
  på kurs (`eld tub 1 kurs 045`) söker den direkt, som en SET-53.
- **Tråden:** den går av när den är utspelad (5,5 nm), efter 15 s över 12 kn, vid en gir på mer än
  90° från kursen vid skottet, eller av sig själv (~1 % per minut). Torpedrummet varnar vid 12 kn och
  60°, och märker genast när tråden går av, men vet bara varför om det var vår fart, gir eller
  trådens längd. Den nya ordern är `kapa tråden [tub N]`. Hörs en fientlig torped medan vår är på
  tråd föreslår torpedrummet `kapa tråden`, så att undanmanövern är fri.
- **Var:** `weapons.py` (`wire_nm`, `guide_torpedo`, `cut_wire`, `_step_wire`, `WIRE_*`),
  `stations/torpedo_room/wire.py` (`WireMixin`, beräknad bana `path`), `Running.legs`. Kortet ritar
  banan bit för bit efter styrordern.
- **Prov:** `tests/test_wire_torpedo.py`. Mot en jagare 3 nm bort i 12 kn som girar 110° en minut
  efter skottet, med plottet uppdaterat var 10:e s: den trådstyrda träffar i minst 4 av 5 frön, en
  rak 53-61 i högst 1 (provkört: 6 av 6 mot 0 av 6).
- **Ytskott mot stillaliggande mål** (`kalibrering/ytskott.py`, 8 frön, radar varje minut i 10 min):
  träffar av 8 på 1–6 nm: ensam 53-61 8, 7, 2, 2, 2, 2; salva (tre 53-61) 8, 7, 4, 6, 5, 5; SET-53 8 ut
  till 4 nm (räckvidden); 53-62T 8, 8, 8, 8, 7, 7. Plottets fel i sidled växer med ungefär 0,7° i bäring
  och passerar träffradien (0,03 nm) strax under 3 nm, även när lösningen är säker. Målsökarnas 8 av 8
  mot stilla mål är troligen för högt (stoppad jagare 137 dB); se `docs/TODO.md`.
- **Kontroll:** `kalibrering/kontroll.py` som baslinjen (35 min på 4 kärnor).

## 2026-11-21 – provspel i 3 timmar: förslag med omdöme

Ett provspel i 3 timmar speltid i alla långa scenarier (ja-kapten som också tittar, skjuter och ger
rutinorder) gav en rad förslag som en riktig besättning inte hade gett. Rättat:
- **Inte upp när de har oss.** Navigatören föreslog fix på periskopdjup och radion antenndjup för
  sambandet med jagaren 0,3 nm bort och pingarna genom skrovet; den som sa ja jojade mellan 220 och 40 m
  med skrovknak och kavitation. Nu säger vakthavande nej (`OfficerStation.vetoes`) till allt som tar oss
  uppåt (periskop- och antenndjup, ytläge, `djup` ≤ 50 m grundare än beordrat, fix, vak, ventilation)
  medan `Knowledge.hunted`; tät rök (≥ 0,7) och nödblåsning undantagna. Vetot prövas också när förslaget
  levereras (`Game._suggestion_stale`), så ett förslag som låg i kön när jakten började släpps.
- **Ingen periskopfix på väg ned.** "Vi är på periskopdjup, föreslår fix" kom sekunden efter en dykorder och
  vägrades sedan. Villkoret ser nu det beordrade djupet, och navigatören säger nej till `fix` på väg ned.
- **Ned, men inte i botten.** Vakthavandes, periskopets och bryggans "föreslår djup 60/100" följer nu
  navigatörens djupgräns (`Station.dive_depth`, som sonar och maskin redan gjorde); i Clyde föreslogs djup
  60 där kortet visade 40 m. Går det inte under periskopdjup föreslås inget djup.
- **Skenmål bara mot oss.** Torpedrummet föreslog skenmål två sekunder efter att sonar sagt "de jagar
  något långt bort, inte oss". Nu på jakttecken (`HuntSigns`), inte på varje tät ping.
- **Samma förslag en gång.** Navigatören och maskin föreslog båda "fart 5, djup 60" inom sekunder; samma
  order från en annan station inom 30 s (`SAME_SUGGESTION_S`) släpps; senare kommer den fram med sitt
  skäl (ett långsamt test visade grundvarningen 45 s efter sonarns "djup 120" släppt, och båten gick på grund).
- **Rapporten före förslaget.** "Föreslår smygmotor" kom före "ny kontakt", "föreslår djup 60" före
  radarvarnaren. `ReportQueue` lägger ett förslag efter rapporter som ligger inom 6 s i kön.
- **Radions statusrad.** Sa "nästa sambandstillfälle kl 09:00:00" kl 09:15. Nu "pågår, från 09:00 till
  09:20" eller nästa som inte börjat, utan sekunder, och "1 meddelande mottaget".
- **Isen.** Navigatören varnar (`nav.suggest.ice_closing`) också medan vi stiger mot en öppning, och på väg
  mot ytläge när för- eller akterskeppet fått is vi inte kan bryta; "för smal" sägs inte om en råk på 250 m
  där vi bara står snett.
- **Mindre tjat under lång jakt.** Plottet säger "har ändrat kurs" om jagaren högst var 30:e min när vi är
  jagade (`HUNTED_MANEUVER_REPEAT_S`; `plot.hunter` säger hur han jagar), och samma förbättring
  ("lösningen är nu säker") sägs inte igen inom 10 min. Torpedrummet säger ingen ny skjutlösning på ett mål
  som våra torpeder är på väg mot; `skjutlösning` utan kontakt väljer hotkontakten med bäst lösning.
- **Fartyg till ankars** fick kurs och fart ur vinkeln på bogen ("fart cirka 3 knop"). Nu "ligger still"
  (ankarljus i mörker), fart 0 och ingen kurs till plottet, och nästa titt säger "som förut".
- **Ärligare kvalitet.** En trupptransport i 6 kn skattad till 2 kn kallades god med "kurs och fart kan vi
  inte säga", och den raka torpeden missade: kurstaket gällde bara skattad fart ≥ 3 kn. Nu när målet kan
  gå (fart + 2σ ≥ 3 kn). `tma_kvalitet.py` (övning/kuba/konvoj-kort/sundet/krig-kort, 8 frön, 120 min):
  god grova fel 6,5 % ⇒ 5,3 %, säker 2,5 % ⇒ 1,7 %, säker > 3σ 9,5 % ⇒ 5,1 %.
Utrett och lämnat: i Arktis kom vi inte fram på 3 h, men navigatören höll kursen mot Nord-7 hela tiden;
branden stoppar turbinen (5 kn) och vi stannar vid råkarna.
Provspelsboten: `kalibrering/provspel.py` (loggarna i `logs/provspel/`).
Tester: `tests/test_suggestion_sense.py`, `tests/test_tma.py`. Kalibrering: `kontroll.py` (passiv och
ja-boten, alla scenarier, 8 frön) som baslinjen: inget utfall flyttat (krig ja hemma 6, förlorad 1).

## 2026-11-21 – stridslarm bara när den pingande jagaren är nära

Jagarens pingar hörs på 50–100 nm, och snabb pingtakt gav stridslarm och förslag om att undvika också
när jagaren jagade något långt bort. Nu bedömer sonar avståndet på pingarnas styrka: snabb takt med
mottagen nivå ≥ 142 dB (~8 nm; under skiktet räknar operatören med 7 dB för skiktet) är som förut
(`sonar.ping.fast`, `HuntSigns`, stridslarm, djupförslag). Svagare ger `sonar.ping.fast_far` ("De jagar
något långt bort, inte oss") utan larm, högst var 15:e minut per pingare; första pingen är då en vanlig
kontaktrapport ("Svaga pingar, långt bort"). Bedömningen är god när styrkan ligger minst ett skikt från
gränsen, annars osäker ("troligen långt bort"). Blir pingarna starka under jakten kommer larmet då.
Bor i `sonar_room.py` (`PING_NEAR_RL`, `_ping_near`). Tester: `tests/test_ping_distance.py`.
Kalibrering: alla scenarier som baslinjen utom krig ja (8 frön) förlorad 0 ⇒ 2, tidsgräns 2 ⇒ 0;
över 24 frön förlorad 2 ⇒ 4 på olika frön (brus från förloppen som skiljer sig), stridslarm 67 ⇒ 60.

## 2026-11-20 – benförslag, pingar från tappad kontakt och botten före samband

Tre gamla buggar som provspelet visade:
- Plottet gav ett likadant benförslag för varje kontakt (fyra konvojfartyg: fyra "kurs 210" på en halv
  minut). Ett nytt ben ger avstånd på alla bäringar, så nu ett benförslag åt gången, högst var 5:e minut
  (`plot.LEG_GAP_S`), också på vakthavandes initiativ.
- "Har tappat S-2" och strax efter "Pingarna från S-2 är mycket starka": sonar känner igen pingaren också
  när kontakten är tappad. Nu säger den att maskinerna inte hörs, bara pingarna (`data["lost"]`).
- Navigatören föreslog botten en minut efter radions förslag att gå upp till sambandstillfället, så båten
  missade telegrammen. Nu inget bottenförslag medan ett sambandstillfälle väntar, om vi inte är jagade.
Kalibrering: alla scenarier som baslinjen utom kuba-kort ja rapporterad 3 ⇒ 5; krig ja hemma 6.
Tester: `tests/test_old_fixes_pings_legs.py`.

## 2026-11-20 – krigspatrullen efter provspel

Rättat efter en timmes provspel och genomlästa telegram:
- Staben sände "RAPPORT SAKNAS … RAPPORTERA OMEDELBART" i samma tillfälle som hemkallelsen ("rapportera
  inte förrän ni är ute"): den väntade fortfarande på spaningsrapporten. Ett telegram med ny uppgift utan
  rapport häver väntan och stryker påminnelserna i kö (`Headquarters.cancel_report_request`).
- Hemkallad låg båten kvar på botten i sju timmar: navigatören föreslog botten igen och utvägen frågade
  aldrig efter fart med hot i plottet. Nu inget bottenförslag när vi är hemkallade (om vi inte är jagade)
  och `kurs …, fart 4` ut när vi ligger still.
- I krig-kort hade vakten inte konvojen vid överlämnandet (9–11 nm, ibland bara handelsfartyg): den
  startar nu 11–13 nm bort och ligger 5–9 nm bort som i konvoj-kort. Sambandstillfällena var 15:e minut
  gav ständiga förslag om flytkabeln mitt i anfallet; nu var 30:e (07.35, 08.05 …).
- Navigatören upprepade "kurs mot konvoj 1" var 15:e minut; nu upprepas kursen bara mot en fast plats
  (ankarplatsen), en konvoj som rör sig kommer själv.
Kalibreringen i `kalibrering/README.md`; krig-kort verktyg sänker nu 3 av 8.

## 2026-11-20 – krigspatrullen (krig, krig-kort)

Nytt scenario utan fast plan: kriget har börjat och K-114 patrullerar kvadrat 14 tills staben kallar hem
den. Ordern ger en konvoj; sedan sänder staben en uppgift i taget vid sambandstillfällena: fartyg till
ankars att fotografera, en landstigningsstyrka att rapportera kurs och fart om, en ny konvoj. Navigatören
föreslår kurs dit (marschfart till en fast plats långt bort), radion föreslår rapporten när plottet har
styrkan och vakthavande periskopdjup och svep nära ankarplatsen. Pejlas en sändning kommer flyget och en
jaktgrupp; en sänkning drar flyget dit. Efter tre uppgifter (eller torpederna nästan slut, skrovet skadat,
kl 16.30) kallar staben hem oss och utvägen gäller; plottet föreslår då inga TMA-ben och navigatören
föreslår marschfart ut. Slutrapporten listar uppgifterna och det sänkta tonnaget. Kort variant: bara
den första konvojen i en mindre kvadrat, sedan hem.

Var: `sim/theatre.py` (krigsskådeplatsen, sanning), `sim/scenario/krig.py`, `sim/radiogram.py`
(`RadioMessage` med `motion`), `TasksOrdered` och `PositionReported.motion/task` (`events.py`),
`Knowledge.order_tasks_t/task_place/photo_t`, `Waypoint.at`, `Scenario.theatre/escape_task`,
`Game.recalled`, `World.open_ended`, `EscapeGoal.requires_flag`, `enemy.df_probability/df_sigma`. Radion
levererar krigsskådeplatsens telegram efter scenariots (`reception.py`) och föreslår rapporten
(`sending._task_report_advice`); navigatören `_task_watch` och `exit_order`; vakthavande
`_photo_task_watch`. Tester: `tests/test_war_patrol.py`. Kalibrering: `kalibrering/krig.py`; ja-boten hemma
5 av 8 (foto 4), verktygsboten hemma 6 (3 konvojer sänkta, 3 foton, 3 spaningar); kort: ja-boten hemma 4.
Fingeravtrycket för alla andra scenarier oförändrat. `kontroll.py` kör nu upp till 15 h.

## 2026-11-20 – appen i ~/Projekt/Lokalt

Ingen ändring i spel. `K-114.app` ligger nu i `~/Projekt/Lokalt` i stället för `~/Applications`, och
`ikon/bygg-app.sh` bygger dit när inget mål anges (README likaså). Appen har kodmappens sökväg inskriven
(startskriptet, länkarna till `.venv`), så den kan flyttas fritt. Det är en flytt av kodmappen som kräver
att den byggs om.

## 2026-11-20 – vyregistret

Ingen ändring i spel. Vyerna var kopplade för hand i `ui/app.py` (en ordmängd per vy, en gren per vy i
`_view_word`, `action_chart` m.fl. och en egen `tab_views`). Nu står de i `ui/views.py`: `ViewDef` med
skärmen, orden, namnet i handboken, villkoret för Tab-ordningen (`ViewContext`: stort fönster, vem som har
befälet, tornluckan) och för loggboken och telegrammen den metod i appen som tar ordet. Handbokens vyord
(`ui/manual.VIEW_WORDS`) kommer ur registret, så bryggan står nu före periskopbilden där som i Tab-ordningen.
Test: `tests/test_views.py` (Tab-ordningen i olika lägen, inget ord öppnar två vyer).

## 2026-11-20 – torpedrummet och radion som paket

Ingen ändring i spel (fingeravtrycket lika). De två största stationerna är delade som navigatören:
`sim/stations/torpedo_room/` (`station.py`, `common.py`, `phrases.py`, `firing.py` med eldledningen som
`FiringMixin`) och `sim/stations/radio/` (`station.py`, `common.py`, `phrases.py`, `reception.py` med
mottagningen och `sending.py` med rapporten och pejlrisken). Paketens `__init__.py` exporterar samma namn
som förut. Torpedrummets tolkning av `ladda tub …` heter `load_order` (var `_load`, samma namn som metoden).

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
