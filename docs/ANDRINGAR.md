# K-114 – ändringslogg

Vad som ändrats, nyast först: vad det betyder i spel, var det bor i koden och vad kalibreringen
visade. Systemen i detalj står i `docs/system/`, siffrorna i `kalibrering/README.md`.

## 2026-11-26 – Bandet skär av målet; plottet låter det vara; grundet "här" eller "framåt"

- Clyde-in (ja-boten): sonar föreslog "kurs mot den, fart 5" var femte minut efter en Polarisbåt i 10 knop, som
  drog ifrån, och plottet föreslog samtidigt nya ben bort från den. Nu föreslår sonar kurs med förhåll ur plottets
  lösning i lägsta fart som minskar avståndet (5 kn, sedan strax under kavitationsfarten), kurs mot dess väg när den
  kommer mot oss men korsar för fort, och säger när den går ifrån oss fortare än vi tyst kan gå
  (`sonar.record.outrun`, inget förslag). Plottet föreslår inga ben på målet medan bandet inte är klart.
  Clyde-in frö 202 med ja-boten: bandet klart (förut slut på tiden). `stations/recording.py`, `stations/plot.py`.
- Navigatörens grund framåt prövas mitt i en gir också längs den beordrade kursen, och djupkvitteringen säger
  "här" eller "0,8 sjömil framåt" (förut "här" också för grundet framåt; sundet-in frö 22 sa navigatören "botten
  cirka 20 meter här" och vakthavande föreslog djup 50 en halv minut senare).
- Kalibreringen (`kontroll.py`, alla scenarier) för dessa och föregående ändring pågår vid commit.

## 2026-11-26 – Plottets ben inte i döda sektorn; torped tystnad tidigt går troligen kvar

- Svansen-kort frö 201 (ja-boten): plottet föreslog "kurs 203" med skuggaren i bäring 015, rakt i döda sektorn
  akterut. Sonar tappade den, och nästa ljud var torpedrören. Nästa ben lägger nu aldrig kontakten inom sektorn
  + 15° (`PlotTeam._suggest_course`, `LEG_BAFFLE_MARGIN_DEG`). `tests/test_tma.py`.
- Duell-kort frö 202 (ja-boten): torpeden tystnade tvärs 80 s efter skottet, och sonar antog att den var borta
  ("tystnar den där vi hör"). Maskin föreslog genast 13 knop, ja-boten sa ja och torpeden hann ikapp. Nu går en
  torped som tystnar före 75 % av gångtiden troligen kvar (`RUNNING_FRACTION`, `sim/stations/incoming.py`): larmet
  står, och sonar säger "håll farten". Maskins sprintförslag säger "på aktiv sonar" bara när det var pingar
  (`Knowledge.pinged_t`). `tests/test_enemy_torpedo.py`.
- Kalibreringen (`kontroll.py`, alla scenarier) pågår vid commit; resultatet förs in här.

## 2026-11-26 – Vrakförslaget går inte genom grundet

- Provspel (ja-boten, sundet-in frö 22): navigatören föreslog "kurs mot vrak 1" och en halv minut senare en gir bort
  från grundet framför oss (`nav.suggest.land`), två gånger. Förslaget prövade bara avståndet och djupet vid vraket.
  Nu måste raka vägen dit vara fri på kortet (`NavigationStation.path_clear`, `sim/stations/navigation/bottom.py`).
  `tests/test_wrecks.py::test_the_wreck_is_not_suggested_through_the_shallows`.

## 2026-11-25 – Utsikten: bryggan och periskopbilden i en vy

- Bryggvyn och periskopbilden syntes aldrig samtidigt (bryggan bara med luckan öppen). Nu är de en vy, utsikten
  (`ui/lookout.py`, `LookoutScreen`; `utsikt`, `brygga`, `periskopbild`): bryggans panorama när bryggan är bemannad
  (eller luckan på väg) och periskopet nere, annars periskopbilden. Kikarens okular på bryggan (förut periskopvyn i
  ytläge) nås med ↓ från panoramat och ↑ tillbaka. Panelerna är `BridgePane` och `PeriscopePane`; vyns tangenter
  följer det som visas. Tab: central → sjökort → sonar → ubåten → utsikten, fem vyer i stället för åtta före
  loggens och översiktens ändring.

## 2026-11-25 – Loggboken är ett lager (PageUp), översikten huvudskärm i alla fönster

- Loggboken var en egen vy i Tab-ordningen (stort fönster) eller huvudskärmen (litet). Nu fälls den ned över den
  vy som är öppen med PageUp och fälls upp med Esc eller PageDown förbi slutet (`ui/logdrawer.py`); orderraden
  behåller fokus, så kaptenen kan läsa bakåt och ge order i sjökortet eller periskopet. `logg` växlar den,
  `telegram` visar bara remsorna, slutrapporten fäller ned den i full höjd. L gick inte: orderraden tar alla
  bokstäver (`läget`, `länsa`, `ladda` …). Översikten är huvudskärm också i små fönster (loggremsan 7 rader,
  9 från 100 × 30); vyerna `LogScreen` och `OverviewScreen` är borta. Tab: central → sjökort → sonar → ubåten →
  periskopbild. Provat i 80 × 24 med `run_test` och skärmbilder; inte i en riktig terminal eller i webbläsaren.

## 2026-11-25 – Vakthavandes "djup 60" glesas ut obesvarat

- Kuba-kort frö 7 på periskopdjup med jagare och flyg: "Föreslår djup 60" sju gånger på sju minuter medan kaptenen
  teg (fartygsradarn och flygradarn turades om, larm glesades aldrig ut). `Station.suggest(..., alarm_backoff=True)`
  fördubblar nu ett obesvarat larms väntan från dess egen cooldown, högst 10 min (`ALARM_BACKOFF_MAX_S`); används
  för vakthavandes och periskopets `off.suggest.down`. Varje skäl har sin egen nyckel, så ett nytt skäl kommer fram.
  Samma spel: 2 förslag på 15 min. `tests/test_suggestions.py::test_alarm_with_backoff_thins_out_but_not_past_ten_minutes`.

## 2026-11-25 – Förklaringarna bryts mellan posterna i 80 kolumner

- Ubåten-vyn i 80 × 24: förklaringen bröts av terminalen mitt i ("····" sist på en rad, "sjökortets djup" på nästa),
  och med höjden 2 syntes raden "Sonar hörde …" och tavlans normalt/varning/fara aldrig. Nu packas posterna efter
  bredden (`profile_render.legend_items`, `pack_legend`; `#boat-legend` har höjden auto, högst 5). Djupmätaren
  säger "ingen lodning" (förut "ekolod ej lodat", som bröts) och klipper i stället för att bryta.
  `tests/test_boat.py::test_legend_breaks_between_items_and_fits_the_width`.

## 2026-11-25 – Plottet tar tillbaka "nu god" när målet manövrerat strax efter

- Kaosboten (krig-kort, clyde-in): "Lösningen på S-2 är nu god" och 1–30 s senare "S-2 har troligen ändrat kurs …
  vi börjar om". Nu släpps ett köat `plot.improved` för kontakten när manövern upptäcks, och har det redan sagts
  inom 2 min (`RECALL_IMPROVED_S`) säger `plot.maneuver` "Lösningen vi nyss gav gäller inte, vi börjar om".
  `tests/test_tma.py::test_maneuver_right_after_good_takes_the_good_back`.

## 2026-11-25 – Radion väntar på djupet för en jagare med dålig lösning eller nyss tappad

- Konvoj-kort frö 5: jagaren var säker på 4,1 nm, plottet började om efter en manöver (dålig lösning, 5,8 nm), och
  radion föreslog djup 40 för långvågen; två minuter senare hade jagaren oss. Nu räknas en jagare eller ubåt som
  nära också på en dålig lösning, med avståndet minus 1σ (högst 30 %, `POOR_NEAR_F`), och en sådan som plottet
  tappat de senaste 15 min (`LOST_RECENT_S`, `_threat_lost`) utan att den säkert var längre bort än 5 nm
  (`radio.wait_lost`). Vakthavandes påminnelse vid tystnad (`idle_proposals`) föreslår inte heller att gå upp då.
  `radio.wait` säger "kanske 5,8 sjömil, lösningen är dålig och den kan vara närmare"; `radio.clear` säger "inget
  hört av S-4 på 15 minuter" eller "plottet har inga hot nära längre" (förut "plottet har nu kontakten på 5,0
  sjömil" när inget hot fanns kvar). `kontroll.py` för kuba-kort, konvoj-kort, krig-kort: som baslinjen
  (kuba-kort ja 3 rapporterade av 8 som förut). `tests/test_report.py`; `test_starpom.py` tar frö 23 (frö 2
  väntar nu på djupet).

## 2026-11-25 – Radion säger när fönstret stänger utan rapport

- Kuba-kort frö 7: jagaren hade oss genom hela sambandstillfället, radion teg (sändningen pejlas) och spelet tog
  slut på `report_missed` utan ett ord. Nu säger radion 5 min före stängning (högst halva fönstret) att rapporten
  inte är sänd och varför (`radio.closing`, `RadioStation._closing_warning`, `CLOSING_WARN_S`): de har oss, hot
  nära, flyget, vi är för djupt, eller "sänd rapport, så går den". `tests/test_report.py`.

## 2026-11-25 – Provspel: sonar mot land för bandet, djuporder under nödblåsning

- Clyde-in (kaosboten, frö 102): sonar föreslog kurs mot Polarisbåten för bandet (`sonar.suggest.record_close`)
  rakt in mot kortets land, och navigatören föreslog genast en gir bort (`nav.suggest.land`), om och om igen.
  Inspelningen prövar nu kursen mot navigatörens `course_safe` som plottet och döda sektorn redan gör
  (`sim/stations/recording.py`). `kontroll.py` för clyde, clyde-in, arktis och arktis-kort: som baslinjen.
  `tests/test_clyde.py::test_sonar_does_not_steer_us_onto_the_chart_land_for_the_tape`.
- En djuporder under nödblåsningen fick "Jest, djup 60 meter", men blåsningen skrev över den och båten låg kvar
  i ytläge. Nu svarar navigatören `nav.depth.blowing` ("nödblåsningen pågår, … nytt djup när vi är uppe").
  `tests/test_ice.py::test_depth_order_during_an_emergency_blow_is_not_acknowledged`.

## 2026-11-25 – Nödblåsning under tjock is: båten låg fast mot isen

- Provspel (kaosboten, arktis frö 102): efter nödblåsning under is som inte går att bryta låg båten på ~13 m mot
  isen resten av spelet. Navigatören sa "Jest, djup 60" men inget hände. Nödblåsningen höll det beordrade djupet
  på 0 tills båten nått ytan, och under isen kom den aldrig dit. Nu tar blåsningen slut när båten stoppas av isen
  (`sim/ice.py`, stötgrenen): `ice.bump` säger "Nödblåsningen är slut, vi vädrar tankarna. Går ned till … meter",
  och nya djuporder lyds. Tunn is i låg fart bryts som förut.
  `tests/test_ice.py::test_emergency_blow_under_thick_ice_ends_against_the_ice_and_we_can_dive_again`.

## 2026-11-25 – Webbljudet i Safari: väcks av sig själv, kön växer när den tar slut

- I Safari försvann ljudet av och till. Safari stänger Web Audio själv (tillståndet `interrupted`, t.ex. när
  talsyntesen tar ljudet, och `suspended` när fliken göms), och sidan väckte det bara vid nästa tangent. Nu väcks
  det så fort det står still och sidan syns: vid varje tillståndsbyte, när fliken syns, efter varje replik och en
  gång i sekunden (`makeAudio` i `web/index.html`; första tangenten eller klicket krävs fortfarande).
- Safari kör Pyodide långsammare, så ett tungt tick kan tömma kön (0,25 s). `WebOut` fyller nu 0,1 s längre fram
  varje gång kön tagit slut, högst 1 s (`AHEAD_STEP_S`, `MAX_AHEAD_S`, `WebOut.ahead`, `underruns`).
- Mätning i konsolen: `k114ljud` (tillståndsbyten, glappen och deras sammanlagda tid; AudioWorklet mäter hur länge
  kön var tom) och `ljudet: …`-rader för byten och glapp ≥ 50 ms. Provat i webbläsarpanelen (Chromium): avstängt
  ljud kom tillbaka direkt utan tangent, sidan låst 600 ms gav ett glapp på 401 ms och kön 0,35 s. Inte provat i
  Safari. `tests/test_webb.py::test_kon_blir_langre_nar_den_tar_slut_men_har_ett_tak`.

## 2026-11-25 – Radio Moskva talar i webben

- Menyns sändningar är inspelade med Milena i `ui/radio/` (sex filer, ~0,8 MB, 11 025 Hz, namnet är textens
  kontrollsumma) av `web/spela_in_radio.py`. `menu_audio.speak_to_samples` tar inspelningen först, så rösten går
  genom mixern och `radio_voice` också i webbläsaren (där talsyntesen inte kan göra ljud) och i terminalen utan Milena.
- Utan tråd (webben) körde sändningen färdigt på en gång: bruset och den sänkta musiken hördes aldrig. Nu
  väntar rösten in ratten med tystnad först, och händelseslingan avslutar sändningen (`MenuSound._off_air`).
  Provat i webbläsarpanelen: ratten 2,5 s, rösten 11 s, brus och sänkt musik tills rösten tystnat.
- `tests/test_menu_audio.py`: varje sändning har en inspelning (och inga gamla ligger kvar), och sändningen utan tråd.

## 2026-11-25 – Webbljudet: en kanal per ljudutgång

- Medan ordern skrevs ut gick menyns ljud (telegrafen, fjärrskrivaren) och spelets samtidigt, och i webben
  delade de en kö i sidans AudioWorklet: blocken varvades (hackigt, dubbelt så fort) och när menyns ljud
  stängdes tömde det spelets kö. Nu öppnar varje `WebOut` en egen kanal (`audio.channel()` i
  `web/index.html`, `start.JsAudio.channel`) och Web Audio blandar dem. Provat i webbläsarpanelen: två
  kanaler med 65 block på 3 s ljudklocka var, menyns stängd vid överlämnandet.
  `tests/test_webb.py::test_menyns_och_spelets_ljud_far_var_sin_kanal`.

## 2026-11-25 – Liv i världen: regn och dimma, vrak, fiske, helikopter, B-36, ljudet ombord, kollision med fartyg

- Kollision med fartyg (`sim/collision.py`): ett fartyg som går över oss på periskopdjup slår i tornet (periskop och
  radio), skrov mot skrov efter den relativa farten; en jagare med skarpa order rammar en ubåt den ser i ytläge (eller med tornet över ytan)
  (`DestroyerAI._ram`); sonar ropar vid stående bäring och stigande styrka. `tests/test_collision.py`.
- Regn och dimma (`weather.Showers`), vrak (`seabed.Wreck`), fisket (`sim/fishing.py`), helikoptern (`sim/helo.py`),
  B-36 (`sim/foxtrot.py`): se `docs/system/hav.md` och `scenarier.md`. Tester: `test_showers.py`, `test_wrecks.py`,
  `test_fishing.py`, `test_helo.py`, `test_foxtrot.py`.
- Ljudet ombord följer skadekontrollen: läckan sprutar, kölsvinet droppar, pumparna dunkar, reparationen slår (eller
  filar tyst i tystnad), fläktarna står i tystnad (`ui/ambience.py`; statusraden `pumps`, `leak_rate`, `repairing`,
  `hushed`).
- Konvojens klassningar på en rad (`sonar.classified.many`).
- Kalibrering (`kontroll.py --spara`, ny baslinje): mot förra baslinjen (3b5637c) flyttade bara jagad ja (frö 2
  förlorad ⇒ undkom) och krig ja (fullföljd 7 ⇒ 5; frö 4 och 5 slutar i tidsgränsen, en förlust som förut).
  Kuba-kort ja (rapporten sänd 3 ⇒ 6 av 8, radions förvarning) ingår i den nya baslinjen. Med helikopterns Mk 44
  förlorade ja-boten 6 av 8 i krig; den är av.
- Buggar längs vägen: efter ett fastnat djuproder låg båten kvar där rodren drivit den (det beordrade djupet följde
  med; konvoj-mot frö 3 blev liggande på 3,6 m och rammades), nu tillbaka till kaptenens djup; fiskebåtar räknades som hot (vakthavande föreslog att vänta på mörkret för en); torpedrummet
  varnade inte för vänliga fartyg nära målet (bara övningens bevakningsfartyg ska undantas); sonars undanmanöver
  föreslog ett djup under det sänkta provdjupet (jagad frö 84); ett förslag och dess eget larm samma sekund (jagad-kort
  frö 4); `länsa` i en torr båt sa två saker; packboxarna tjatade på besättningens egna 280 m (krig frö 2).

## 2026-11-25 – Skadekontrollen: läckor, avdelningar, länspumpar, reparation och belastning

Vad det betyder i spel (`docs/system/besattning.md`, Skadekontrollen; `sim/damage.py`, `stations/damage_control.py`):
- Skadan sitter där laddningen small: akter om oss rodren och nionde avdelningen, förut sonaren och tuberna. Haverilarmet
  säger var ("Lätta skador vid nionde avdelningen: rodren. Vatteninträngning i nionde, skotten stängda").
- Läckor med sort (packbox, rörgenomföring, svetsfog, spricka) ger mer vatten ju djupare vi är och tätas av avdelningens
  folk, aldrig av sig själva; en spricka läcker kvar, och maskin föreslår då ett djup där pumparna tar det.
- Vattnet ligger i sin avdelning (genomskärningen visar det, skotten gula när de är stängda) och lutar båten; halvfull lämnas
  avdelningen. Saltvatten i batteriet ger kortslutning och brand i andra avdelningen.
- Länspumparna tar mindre på djupet, hörs och står i tystnad tills vattnet blir farligt (`länsa`, `läns stopp`).
- Maskin lagar en sak i taget i sin ordning eller kaptenens (`reparera roder`), hörbart med slag eller tyst i halva takten;
  svåra skador och saltvatten går inte att laga helt till sjöss. Systemtavlan visar läckorna, pumparna, skotten och provdjupet.
- Ett skadat skrov sänker provdjupet (och krossdjupet); besättningens gå-ned-förslag håller sig ovanför. Skrovet nöts som
  förut bara under det konstruerade provdjupet (mot det sänkta gav det en ond cirkel: jagad frö 63).
- Djuprodret kan fastna (maskin föreslår back 5), skadad framdrivning hörs.
- Fel av belastning: tryckvågor gör snabbstopp och ångläcka vanligare en tid, full fart i 20 min värmer lagren (30 min:
  de skär), kavitation gröper propellern, djupkörning nära provdjupet får packboxen att släppa. Maskin varnar och föreslår först.

Buggar hittade längs vägen: ett larm att gå ned med samma djup som förslaget som stod svaldes (jagad frö 3, sonars skäl
"så att de tappar ekot" försvann); "Vi lagar …" kom före haverilarmet om samma skada; provdjupet ropades ut tre gånger på
tio sekunder under bomberna. Tester: `tests/test_damage.py` (31), `tests/test_suggestion_sense.py`.

## 2026-11-25 – Buggjakt med botarna (frön 61–72)

- `ytläge` kraschade spelet när plottet hade ett örlogsfartyg utan lösning före ett hot med lösning inom 4 nm
  (navigatörens fråga om ytläge nära fienden jämförde avståndet med None). Kaosboten, krig-kort frö 71.
  Ett uppmätt avstånd går nu före ett okänt. `NavigationStation._threat_near`.
- Sonar: två avlägsna pingare 9° isär som pingade med 4 s mellanrum slogs ihop till en pingare med falsk
  bäringsdrift, och "Aktiv sonar … Någon söker" kom tre gånger på 46 s (konvoj frö 63, skyttebotens logg).
  Pingar tätare än 6 s (jagaren pingar högst var 6:e s) som skiljer sig mer än 8° är nu två pingare
  (`PING_MIN_GAP_S` 4 ⇒ 6).
- Översikten: "Samband nästa 05:00, om 29 min" och "Tiden ut … 45 min kvar", inte "om 0 h 29 min" (`fmt.duration`).
Tester: `tests/test_playtest_fixes.py`, `tests/test_overview.py`.

## 2026-11-25 – Förbättringar efter provspelet

- Torpedrummet varnar för en kontakt utan lösning vars bäring drar in över den målsökande torpedens kurs under
  gångtiden (operatörens bäringsdrift). Skyttebotarna (`skytt.py lyssna alla 24-31`): clyde-in frö 28 sänkte ett
  handelsfartyg 12° från banan som drog 5°/min mot den, utan varning; nu varnas det och boten avstår.
  `skytt.py ja`/`skjut` frön 24–31: inga larm. `FiringMixin._bearing_crosses`.
- Översikten: bäringsdriften i kontakttabellen (▸/◂ och °/min), nästa sambandstillfälle under UPPDRAG (radion).
- Vattenfallet: etiketterna får en ledig ruta före och efter ("S-7S-3" i en smal spalt).
- Centralen: på en hög vägg står klockan i raden med de mindre instrumenten och fartmätaren får hela rutan.
- Maskin säger varför det slamrar: den branta vinkeln, eller trimmens lutning från 2°.
- GitHub: Pages bygger och publicerar i två jobb (paketet hittades ibland inte i samma jobb); kalibreringskontrollen
  körs varje söndag och för hand (`.github/workflows/kalibrering.yml`) och är röd när något flyttat.
- `kalibrering/talniva.py`: hur mycket varje talnivå läser upp, och vad (för finjustering efter provspel med ljud).
Tester: `tests/test_firing_rules.py`, `tests/test_overview.py`, `tests/test_sonar_view.py`, `tests/test_instruments.py`,
`tests/test_pitch.py`.

## 2026-11-25 – Provspel: översikten i 100 kolumner, kontakttabellen smal, mätarnas etiketter, skott i lutning

- Huvudskärmen i ett 100 kolumner brett fönster gav översikten bara en spalt (panelen får 98 kolumner, gränsen var
  100): sjökortet, vattenfallet och profilen syntes inte. Gränsen är nu 90 (`TWO_COL_W`).
- Kontakttabellen i en smal spalt (under 60 tecken, `COMPACT_W`) kapade kvaliteten ("osäke", "dål"): nu kortas
  klassningen först och lösningen skrivs kort (`2,3nm 218/10,7`); kvaliteten och tappad (∅ i smalt läge, som i
  sonarvyn) får alltid plats, i linje.
- Mätarnas etiketter krockade i små mätare (telegrafens "SAKTA HALV" blev "SAKTHALV"): en etikett som skulle krocka
  med en tidigare ritas inte (`draw_dial`).
- Skyttebotarna (`skytt.py skjut alla 24-31`, 176 spel, inga larm från oraklet) fick 8 skott nekade för lutningen:
  skjutdjupet beordrat och skottet direkt efter. Nu väntar kaptenens skottorder tills båten är rak och skjuts då
  ("Vi skjuter när den är rak", högst 2 min, `LEVEL_WAIT_S`).
Tester: `tests/test_overview.py`, `tests/test_instruments.py`, `tests/test_pitch.py`.

## 2026-11-24 – Stampvinkeln: båten lutar när den byter djup

- Båten lutar när rodren byter djup: cirka 13° i 12 kn, ingen lutning under 2 kn (barlasten), fören 20° upp vid
  nödblåsning. Syns på centralens lutningsmätare, libellen, panelen TRIM och i statusraden.
- Navigatören väljer brant vinkel när fienden har oss eller en torped är i vattnet: djupbytet går 1,4× fortare
  (högst 2,8 m/s), ~19°, och kvittensen säger "Brant vinkel". Bara ned: uppåt slamrade det och eskorten hörde oss.
- Över 15° far lösa föremål i durken: maskin säger det, det hörs i vattnet (135 dB, jagare pejlar det), märket ≡ i
  plottet och sonarvyn. En gång per brant läge.
- Torpedrummet skjuter inte med mer än 7° lutning.
Var: `sim/ownship.py` (`pitch`, `_pitch_step`, `steep`), `NavigationStation._steep`, `hull.clatter` i
`stations/engineering.py`, `MAX_LAUNCH_PITCH`. Tester: `tests/test_pitch.py`.
Kalibrering (`kontroll.py`): krig ja hemma 4 ⇒ 7 av 8, jagad ja undkom 6 ⇒ 7, duell ja undkom lika ofta men
långsammare (median 54 ⇒ 93 min); övrigt som baslinjen. Ny baslinje sparad (`kontroll.py --spara`, 2026-11-25).

## 2026-11-24 – Översikten är huvudskärmen, centralen på hela skärmen med fler instrument

- Huvudskärmen är översikten med loggremsan (9 rader) och djupmätaren under, från 100 × 30 tecken. `Esc` och
  `översikt` går tillbaka dit. I mindre fönster fyller loggen skärmen och översikten är en vy först i Tab-ordningen.
- Centralen är en egen vy på hela skärmen (`central`, först i Tab-ordningen i stort fönster; `ui/central.py`). Inga
  besättningsfigurer: snabbtelefonens panel med en lampa och namn per station visar vem som talar.
- Fler instrument på en hög skärm: LUTNING (дифферент), TRIM (rodrens last), BATTERI och LÄNS (vatten i båten), i en
  rad under de stora (`Geometry.strip_rows`, `ui/instruments.py`).
- Borttaget: den lilla centralen bredvid loggen och `CentralView`; `CENTRAL_WORDS` (ordet `central` öppnar vyn).
Tester: `tests/test_central_render.py` (layouten), `tests/test_instruments.py`, `tests/test_views.py`, Tab-testerna.

## 2026-11-24 – Talnivå: allt läses inte upp (loggen har allt)

- `tal viktigt` (standard), `tal allt`, `tal larm`, `tal av`, och "Uppläsning" i inställningarna. Loggen har alltid
  allt. Viktigt: larm, förslag, kontakter, lösningar och svar; inte rutinen (sonarens bäringar, "hörs igen", "djupet
  nått", trimmen klar, dagsljuset).
- Kvittenserna läses bara "Есть" (Jest), utom med `tal allt`.
- Samma sak från samma station om samma kontakt läses inte igen inom 3 min speltid om inte kvaliteten ändrats.
- Tidskomprimering: från ×2 tystnar rutinen, från ×8 allt utom larm och förslag.
- Larm och förslag läses alltid (utom `tal av`), också upprepade (testat).
- Mätt med ja-boten i sex scenarier: `tal viktigt` läser upp 42 % mindre än `tal allt`, `tal larm` 66 % mindre; loggboken har allt som förut.
Var: `ui/audio.py` (`speech_rank`, `SoundBoard.wanted`, `set_level`), `ui/app.py`, `ui/settings.py`.
Tester: `tests/test_speech_level.py`.

## 2026-11-24 – Översikten: allt kaptenen vet på en skärm

- Ny vy `översikt` (eller `lägesbild`), först i Tab-ordningen. Undantag från regeln om inga nya vyer:
  den samlar de andra. Sjökortet kring oss (skalan rymmer kontakterna), vattenfallet 10 min och djupprofilen till
  vänster; kontakttabellen, uppdraget, periskopet, bäringsrepeatern och systemtavlans paneler till höger.
- Kontakttabellen: plottets kontakter, hot först, med klassning, bäring och, där sjökortet visar lösningen, avstånd,
  kurs och fart framräknade till nu och kvaliteten; tappade nedtonade i 30 min. Ny krok `Station.overview_items()`,
  `Game.overview()`, datan i `sim/overview.py` (kunskap, importtestet). Att läsa vyn ändrar inte spelet.
- UPPDRAG (vakthavande): ordern, tiden ut och kvar, fienden har oss / fiende i närheten. PERISKOP: gradringen.
Tester: `tests/test_overview.py`, `tests/test_views.py`.

## 2026-11-24 – Centralen renodlad: bara egna instrument

- Centralen visar bara den egna båten. Bäringsrepeatern på gyrot och periskopets gradring (`PERISKOP 047 · titt`)
  är borta därifrån; de flyttar till översikten (nästa steg). `render_central` läser aldrig plottets kontakter
  (`test_no_contacts_in_the_central`).
- Renderaren delad: `ui/central_render.py` är scenen (rummet, figurerna, periskopet, lamporna, rök och vatten),
  `ui/central_instruments.py` instrumenten (`rudder_angle`, `plane_angle`, `Needles`, julgranen `openings`,
  `draw_instruments`). `CONTACT_STYLE` bor i `ui/styles.py`.
- Två storlekar i stället för tre: lådmätarna i den lilla bilden är borta (huvudraden visar djup, kurs och fart);
  väggarna har rör med ventilrattar. Mellanstorleken (lådmätare skalade upp till 100 × 22) användes aldrig i spelet.

## 2026-11-24 – Enklare ordergivning: j/n, ja på frågor, babord/styrbord, "Menade ni …?"

- `j` och `n` räcker för ja och nej (`SUGGESTION_COMMANDS`).
- Frågar en station om kaptenens egen order ("Svara ja om vi ska skjuta": fredstid, neutrala i banan, för nära, lång
  gångtid, nödblåsning utan vatten, dykning i fjorden, ytläge med fiende nära) verkställer `ja` den, som att upprepa
  ordern; `nej` släpper den. Stationen anropar `Game.asked()`; `Game.active_question` (60 s, `QUESTION_S`) gäller om
  frågan är nyare än ett väntande förslag och syns i orderraden. Kärnladdningen kräver fortfarande upprepad order.
- `styrbord 30`, `babord 30` (`sb`, `bb`, `gira babord 30`): gir från beordrad kurs; navigatören räknar kursen
  (`TurnBy`, ny krok `Station.resolve` före `intercept`).
- En felstavad order ger "Kapten? Menade ni \"periskopdjup\"?" som förslag, så att `ja` verkställer det
  (`CommandRegistry.guess`: ett ord bytt mot närmaste i ordförrådet med `difflib`, eller två ihopskrivna). Aldrig
  vapen eller avbryt uppdraget (`Order.WEAPON` på eld, salva, kärnvapenrådet).
Tester: `tests/test_order_shortcuts.py`.

## 2026-11-24 – Torpedrummet varnar för fiskebåtar och för handelsfartyg sonar tappat nyss

Oraklet (skjut/lyssna, frön 24–31): i clyde-in frö 29 tog en målsökande SET-53 fiskebåten S-1 utan varning.
Torpedrummet varnade bara för kontakter klassade som handelsfartyg som sonar hörde just då; S-1 var klassad som
fiskebåt och tappad 10 min före skottet, 35° från banan. Nu räknas fiskebåtar som neutrala i varningen
(`FiringMixin._neutral`), och ett neutralt fartyg tappat de senaste 15 min (`LOST_LANE_S`) med sista bäringen inom
45° från banan (`LOST_CONE_DEG`) ger varningen med "tappad för N min sedan". Clyde-in frö 28 (ett handelsfartyg som
sonar aldrig hört, träffat efter 9 min gång) är kvar i oraklet: det fanns inget att varna för. Ja-boten: inga larm
på 176 spel.

## 2026-11-24 – Webbversionen publiceras vid push till main

`.github/workflows/pages.yml` körs nu också vid push till main när `sim/`, `ui/`, `web/` eller `ikon/` ändrats (det som
hamnar i webbversionen); bara dokumentation publicerar inget. För hand som förut (`workflow_dispatch`).

## 2026-11-24 – Vaken: stilla under en bit nyis går vi till öppningen som duger

Maskin föreslog "öppning 10, 190 m" och ordern `vak` stoppade under en ny bit nyis på 20 m som isen drivit in över
oss (arktis frö 16): för smal, och förslaget och ordern talade om olika öppningar. Nu går navigatören, när vi nästan
står stilla under nyis kortare än båten, till den bästa loggade öppningen (`_go_to_opening`): den som maskin och
radion nämner. Ordern är densamma. Arktis och duell som baslinjen.

## 2026-11-24 – Vaken: en kort råk med nyis är inte värd att backa till

Oraklet efter vakändringen (arktis frö 16): navigatören mätte upp en råk med nyis på 50 m och backade dit, fast nyis
kortare än båten varken går att bryta igenom eller ta masterna genom; tjock is, och sedan ändå öppning 7 strax
akterut. Nu säger navigatören att den är för kort och går till den öppning han annars skulle välja
(`nav.vak.too_short`, `_measure_opening`), eller söker vidare i 3 kn. Arktis ja-boten (8 frön): stationen nådd
6 ⇒ 7; duell som förut.

## 2026-11-24 – Öppningen som isen drev in över stryks

Oraklet (ja-boten, frön 16–23, 176 spel) gav ett larm: arktis frö 21, "vak" 4 gånger på 15 min medan isen drev in
över oss på periskopdjup. Navigatören räknade öppningen vi låg stilla under som "nyss passerad" och gick tillbaka
dit: tjock is. Nu stryks en öppning som stänger medan vi ligger stilla med tjock is ovanför (`OpeningNotFound` i
`_sound_ice`), så att varken navigatören eller maskin föreslår den igen. Övningen frö 19 tjatar inte längre om
"kurs mot övningsområdet".

## 2026-11-24 – Lätta från botten också utan reaktorn

Bombade på botten föreslår maskin att lätta (`eng.suggest.lift`), men bara med reaktorn i drift: krig frö 4 lade sig
på 152 m, tryckvågen snabbstoppade reaktorn, och vi låg kvar i 20 min tills de sänkte oss. Nu föreslår maskin att
lätta på elmotorn, så fort det går utan kavitation (`EngineeringStation._sprint(lift=True)`); utan botten ingen
sprint på batteriet som förut. Frö 4 lättar nu men förloras ändå (två jagare i kontakt, 3 kn). Kontrollen visade
också långa krig med ja-boten 7 ⇒ 4 fullföljda av 8: frön som byter utfall åt båda håll, som krig-kort.

## 2026-11-24 – Vaken: mät upp råken och lägg dig i mitten

"Stoppa här" (`vak`) under en råk i fart stoppade på stället: i 5 kn glider vi ~130 m, förbi råken, och
navigatören gick ut 250 m och vände ("Vi gled förbi öppningen", arktis frö 21: fyra försök på 16 min). Nu saktar
navigatören till 1,5 kn rakt över råken ("mäter upp den"), och när isekolodet ser tjock is igen går han back 2 kn
till mitten och stoppar där (`navigation/ice.py`, `_measure_opening`, `_back_to_centre`). Omkastningen görs under
2 kn, så den inte hörs; i beskedet säger navigatören att back i maskin stoppar fortare men hörs, och slår kaptenen
back under mätningen behåller navigatören vaken och stoppar oss i mitten (eller där vi står, om råken fortsätter
förut). Backen som broms direkt (provad förut) ställde oss i kanten där råken började.

Frö 21: ytläge genom nyis på första försöket tre gånger, och vid Nord-7 utan glid. Arktis ja-boten (8 frön):
stationen nådd 5 ⇒ 6, arktis-kort 2 ⇒ 3; passiva oförändrade. Tester: `tests/test_icemap.py` (råk på 90 och
190 m tvärs kursen i 5 kn, kaptenens back före och efter att slutet syns).

## 2026-11-24 – Krig-kort: färre fullföljda patruller var slump

Ja-boten på 32 frön gav 10 `patrol_done` på 3c9ce48 och 5–6 efter provspelets andra omgång. Frö för frö bytte
12 av 32 frön utfall, åt båda hållen, och flödena skiljer sig redan efter några minuter med en rapport 1–2 s
senare (frö 0 och 8, `skillnad.py`); de fullföljda patrullerna slutar 127–172 min av 175, nära gränsen. På 64 nya
frön (32–95): 3c9ce48 12, nuvarande 14. Över 96 frön 22 mot 20: ingen verklig skillnad, ingen ändring.

## 2026-11-24 – Provspelet, omgång två: förslag som slutat gälla, pingarna, skjutdjupet

Oraklets botar (ja, skjut, lyssna) på frön 16–23 i alla scenarier, och rapporttätheten i loggarna.

**Förslag som slutat gälla** (`Game._drop_vetoed`): ett obesvarat förslag som en station nu säger nej till dras
tillbaka med systemraden "Förslaget gäller inte längre". Maskin säger nej till `turbin` när reaktorn inte är i
drift: jagad frö 61 och krig frö 21 föreslog att lätta med turbinen, reaktorn snabbstoppade, och ja gav "turbinen
kan inte köras".

**Två pingare en sekund isär** (`SonarRoom._on_sound`, `PING_MIN_GAP_S` 4 s, `PING_DOUBLE_DB` 2 dB): krig-kort
frö 17 hade två jagare 5° och 4 dB isär som pingade med en sekunds mellanrum. De blev en pingare i "snabb takt"
med 2°/s drift, och varannan ping blev en ny: "Någon söker" 15 gånger och "de har kontakt med oss" 11 gånger på
10 min. Nu är två pingar så tätt samma pingare bara på samma nivå och bäring (jagarens dubbelping vid nytt datum),
och driften räknas inte ur dem.

**Skjutdjupet efter jakten** (`NavigationStation._fire_depth_watch`): krig-kort frö 12 kom till skjutläget samma
sekund som kaptenen valde sprinten till 220 m; förslaget om 90 m släpptes (kaptenen hade beslutat) och sedan sa
ingen något. Nu föreslår navigatören `djup 90` när jakten lugnat sig och målet ännu inte är tvärs. Oraklets
`skjutläge_för_djupt` larmar inte längre när de har oss (då är djupet kaptenens val).

**Bevakningsfartyget girar** (`Knowledge.resolve`, `PATROL_MANEUVER_Q`): övningens bevakningsfartyg går ben på 2,5–4,5
nm mellan slumpade punkter och räknas med processbrus q = 10 (först 30, men då blev torpedövningens lösning för sällan
god: 2 av 4 skott i ovning-kort; med 10 goda grovt fel 3,2 % ⇒ 2,6 %, säkra 0,4 % ⇒ 0,2 %, 24 frön). Ovning frö 20 kallade det säkert på 3,8 nm kurs 249 när det låg
på 1,5 nm kurs 170, rakt mot oss efter en lucka på 6,5 min. Ovning, 24 frön: goda grovt fel 3,2 % ⇒ 2,0 %, säkra
0,4 % ⇒ 0 (2 % färre säkra). En längre spärr efter luckan (luckans längd) provades och gav inget.

**Konvojen** (mellansteg, kontrollen inte klar): fartyg som går i grupp räknas som sicksackande redan innan plottet
känner konvojen (`Knowledge.grouped`: minst två andra hållna fartyg inom 25° i bäring de senaste 5 min; konvoj, 24
frön: goda grovt fel 28 % ⇒ 21 %, krig-kort 5,3 % ⇒ 5,8 %, utfallen i krig-kort lika med och utan). Sonar säger
konvojen som en enhet (`SonarRoom._say_convoy`): tappad helt och hörd igen alltid, "hör N av M fartyg" högst var
10:e min. Övningsledaren skickar oss inte vidare när vi ligger inom 0,5 nm från områdets mitt (ovning frö 19:
cirklar kring mitten i 35 min). Back i maskin under en öppning i isen provades och togs bort (se TODO).

**Mindre:**
- Maskins sprint går inte fortare än turbinen orkar med skadorna (`OwnShip.turbine_max_speed`; krig-kort frö 20:
  "fart 11", högsta 9,8).
- Navigatören föreslår ingen bottenfix på väg ned mot botten eller under 2 kn (kuba frö 16: nekad direkt).
- Övningsledaren föreslår inte `kurs mot övningsområdet` när vi redan styr dit (ovning frö 19: fyra gånger på 15 min).
- Vakthavande föreslår ingen titt på konvojen 15 min efter att flygradarn var nära (`AIR_HOLD_S`; krig-kort frö 18:
  upp, flyget, ned och upp igen fyra gånger på 19 min).
- Samma anmärkningar vid inspektionen inom 15 min: "inget nytt sedan förra inspektionen" (jagad frö 3: samma långa
  rad sex gånger på 20 min).

## 2026-11-24 – Utredningarna och provspelet: pingarna, plottets lucka och spann, botten, isen

**Pingarna** (`SonarRoom._on_sound`): två jagare i nästan samma bäring slogs ihop till en pingare, och en
pingares bäringsdrift räknades fram hur länge som helst. Jagad-kort frö 51: S-2:s gamla drift över 6 min
flyttade den 38°, och när den passerade över oss blev den "Någon söker" igen. Jagad frö 51: en nära passages
−1,7°/s över 91 s gav 55° fel, ny pingare 2 s efter "har tappat S-2". Nu räknas driften fram högst 30 s
(`PING_RATE_HORIZON_S`); efter ett längre uppehåll börjar pingarens bäring om, och två pingare i grinden skiljs
på styrkan (`PING_LEVEL_DEG_PER_DB`). Provspel 2 h, frön 1–8: "Någon söker" jagad 22 ⇒ 17, jagad-kort 20 ⇒ 17,
konvoj-kort 2 ⇒ 0 (det som är kvar är mest de första pingarna); "pingtakten ökat" utan beteckning 11 ⇒ 6, 9 ⇒ 6,
3 ⇒ 1.

**Luckan i plottet** (`knowledge.GAP_S` 600 ⇒ 180 s): övningens bevakningsfartyg girade 150° under 6 min utan
bäringar och kallades säkert 3 s efter att sonar hörde det igen (ovning frö 7, 5,0 nm kurs 003, sant 3,5 nm kurs
157). Nu är en lösning över en lucka > 3 min ett steg lägre i 5 min efter luckan. Mot sanningen (ja-boten,
ovning/kuba/konvoj-kort/sundet/krig-kort, 8 frön): goda grovt fel 5,2 % ⇒ 3,2 %, > 3σ 6,2 % ⇒ 4,6 %; säkra
lika många, grovt fel 0,4 %. Oraklet, ovning 16 frön: inga larm (förut 1 av 12). `tma_kvalitet.py` tar `GAP_S`
från miljön.

**Botten igen efter bomberna** (`navigation/bottom.py`, `SETTLE_AFTER_BOMBED_S` 30 min): jagad frö 61 la sig på
botten, blev bombad där, lättade, och 9 min senare föreslog navigatören botten igen med samma jagare ovanför
(sänkta där). Har skarpa laddningar fallit nära medan vi låg på botten föreslås botten inte igen under jakten på
30 min. Jagad, ja-boten, 32 frön: räddade 21 ⇒ 23, förlorade 11 ⇒ 9.

**Tappade och åter hörda på en rad** (`SonarRoom`, `LOST_BATCH_S` 5 ⇒ 20 s glidande, högst `LOST_BATCH_MAX_S`
60 s): en konvoj vid hörgränsen gav fyra "har tappat" på 50 s. Nu samlas de tills ingen ny kommit på 20 s, och en
kontakt som hörs igen (eller tappas igen) innan raden sagts nämns inte. Provspel frö 61–62: krig-kort 111 ⇒ 75
rader, konvoj-kort 51 ⇒ 33, övriga oförändrade.

**Säker kräver tid** (`knowledge.SURE_MIN_SPAN_S` 20 min): oraklet hittade konvojens fartyg säkra på 0,7–1,2 nm efter
6–10 min bäringar när de låg på 2,8–3,7 nm, kursen 100–180° fel (konvoj frö 1, 4, 5). Mätt mot sanningen per spann:
säkra på 8–20 min grovt fel ~10 %, på över 20 min 0 %. Nu är en lösning säker först när bäringarna spänner 20 min,
om inget avstånd mätts i fönstret (periskop, radar, aktiv sonar). Ja-boten, konvoj/konvoj-kort/krig-kort/kuba/ovning/
sundet/duell-kort, 8 frön: säkra grovt fel 2,9 % ⇒ 0,4 %, > 3σ 3,6 % ⇒ 0,4 % (konvoj 15 % ⇒ 0, krig-kort 8,8 % ⇒ 0),
16 % färre säkra; goda 6,3 % ⇒ 6,6 %.

**Under isen, förslag som krockade** (arktis-kort frö 3): navigatören föreslog öppning 6 och 6 s senare "sök vidare";
maskin föreslog "gå till öppning 4" sekunden efter navigatörens ytläge genom nyisen. Nu föreslår ingen av dem något
annat medan ett förslag står obesvarat (`engineering._smoke_advice`, `navigation/ice._ice_advice`).

**Webbversionen:** ljudet är på från början, som i terminalen (hörs efter första tangenten eller klicket).

## 2026-11-23 (kväll) – Provspel i alla scenarier: torpeden i döda sektorn och det som hittades på vägen

Provspelat med orakelbotarna (`skytt.py`, alla lägen, frön 8–15), provspelskaptenen (`provspel.py`, alla 22
scenarier) och kaosboten (44 spel, inga undantag). Varje fynd har ett test.

**Torpeden i döda sektorn** (den allvarliga): springer vi ifrån en fientlig torped hamnar den rakt akterut och
sonar tappar den. Förut släppte torpedlarmet efter 5 min och maskin föreslog lägre fart (kavitation), sonar 4 kn
och en lyssningsgir, med torpeden kvar bakom oss (Svansen-kort frö 31: förslaget kom med torpeden 0,2 nm bakom,
ja ⇒ sänkta). Nu säger sonar att den ligger i döda sektorn och troligen går kvar, och larmet gäller 12 min från
första bäringen (`incoming.py` `TORPEDO_RUN_S`, `Knowledge.torpedo_astern_until`). Duell-kort, ja-boten, 16 frön:
förlorade 13 ⇒ 6; Svansen-kort 3 ⇒ 2; jagad oförändrad.

**Plottet:** en ubåt i undervattensläge (`submerged_submarine`) och konvojens eskort räknas som sicksackande
(q = 30). Duell-kort: goda lösningar på ubåten grovt fel 69 % ⇒ 50 %, kurs > 90° fel 56 % ⇒ 17 %; konvojerna:
säkra men grovt fel lösningar på jagarna 7 ⇒ 3. Ett avstånd med större σ än avståndet sägs inte i siffror ("kan
vi inte säga ännu", förut "cirka 24,6, någonstans mellan 0,2 och 53,2").

**Förslag som krockade:**
- Samma order från samma station med ett annat skäl (vakthavande: flygradar, 11 s senare radar, båda djup 60).
- Masterna föreslogs sekunder efter att kaptenen beordrat oss ned (sonars djup 120, vakthavandes periskopdjup);
  nu inte de första 2 min (`DOWN_ORDER_HOLD_S`).
- "Gå ned" släpps när ett obesvarat förslag redan tar oss djupare (maskins sprint till 220 m skrevs över av
  "djup 60").
- Smygmotor föreslogs samma sekund som jakten började (maskin uppdateras före sonar) och kom efter "de har oss";
  nu veto när vi är jagade. Sonars fart 4 ges inte på begäran under jakt, och vakthavande kallar då inte läget lugnt.
- Maskins sprint upprepades var 10:e min när vi redan sprang (8 gånger på 90 min); kavitationsrådet räknar farten
  på djupet vi är på väg till.
- Sonar föreslog "djup 120 under skiktet" i ytläge med bryggan bemannad.
- Navigatörens "fart 3, djup 90" i skjutläget säger risken när de har oss.

**Under isen:** vak går tillbaka till en öppning vi lämnat de senaste 90 s ("stoppa här" kom under en 30 m råk,
ordern när vi glidit förbi: "ingen öppning loggad") och tar en som dög för en minut sedan; maskin säger inte "ingen
öppning" strax efter att ha föreslagit en; en öppning där ytläget misslyckades stryks; omläggningen går mot mitten
och hoppas över när vi redan står där (förut "lägger oss mitt i den" två gånger på en sekund). Arktis frö 8 ventilerar
nu i stället för att röken blir livsfarlig.

**Rapporterna:** ett svep med fyra eller fler kontakter (periskop, brygga, radar, aktiv sonar) blir en talad rad och
en tabell (`stations/sweep.py`); flera "hörs igen" samlas; en salva säger sina tuber på en rad; antal med ord och
rätt form ("ett civilt fartyg", "en jagare som eskort", "en minut").

**Annat:** okända pingare följs med sin egen bäringsdrift (sundet frö 51: ett nära fartyg gav fem "Någon söker" och
fem stridslarm på två minuter); en gir ut och tillbaka räknas inte som rak gång; lyssningsgiren väntar dubbelt så
länge efter varje tom lyssning (10, 20, 40 min; Clyde: var 15:e min hela natten) och kommer inte när vi håller
"kurs mot …" (övningen: ping-pong med vakthavande var tionde minut); anfallet styr på lösningen 5 min efter tappad
kontakt och säger varför det slutar; plottet föreslår inget nytt ben medan navigatören styr (krig-kort: plottets ben
avbröt anfallet, som föreslogs tre gånger); navigatören föreslår inte vägen ut medan vi går till en öppning (duell:
vaken avbröts och sambandstillfället missades); trimmaren föreslår aldrig mer fart än maskinen har ("fart 6" på
smygmotorn); en torped med stilla bäring vars nivå inte stiger "kommer inte närmare" (kretsar kring skenmålet),
utan larm och ny undanmanöver (duell-kort: åtta minuter av "den kommer mot oss!"); fartyg under 3 kn blir ingen
konvoj; "sök vidare" levereras inte medan vak pågår, och med rök i båten är en smal öppning vid stationen för
masterna (periskopdjup och ventilera före ytläget).

**Kalibreringen** (ny baslinje, `kontroll.py --spara`, commit cc8eb9e; ja-boten): arktis stationen nådd 3 ⇒ 6 av 8
(förlorade 2, båda röken efter branden), duell-kort förlorad 6 ⇒ 4, konvoj-kort konvojen missad 4 ⇒ 1 av 16, duell
ute 6 ⇒ 4 (resten kvar vid tidsgränsen, ingen förlorad), arktis-kort stationen 3 ⇒ 2; övrigt som förut.
Slowtesterna: 1161 gröna.

## 2026-11-23 – Döda sektorn akterut i alla scenarier, buggjaktens verktyg och det de hittade

**Döda sektorn överallt** (`OwnShip.baffle_deg` = `BAFFLE_DEG` 30°, förut bara Svansen): rakt akterut hör sonar
12 dB + 1,5 dB/kn över 4 kn sämre. Det som behövdes för att det skulle fungera i alla scenarier:
- Sonars lyssningsgir (`sim/stations/baffles.py`) föreslås inte när navigatören styr (anfall, följa, farleden,
  vaken), medan ett hot hålls i plottet (Kuba: 4 kn med jagaren pingande på 2 nm) eller mot kortets land (båda
  sidorna prövas med `course_safe`).
- Ny: en kontakt vi tappat nyss som ligger akterut ger en gir som lägger den tvärs (`sonar.suggest.astern_lost`),
  en gång per tappning, bara för fartyg vi vill höra (övningsfartyget, stora fartyg, Polarisbåten i ytläge; inte
  jagare, ubåtar under ytan eller handel: i Svansen gav giren tillbaka lösningen och ubåten sköt). Utan den låg
  övningens bevakningsfartyg akterut hela lyssningsövningen (ovning-kort klar 8 ⇒ 3).
- Bandspelaren: Polarisbåten akterut utan färsk bäring ⇒ sonar föreslår kursen mot sista bäringen.
- **Gammal bugg:** lyssningsgirens plan glömdes 5 s efter förslaget (tiden räknades från när vi började gå rakt,
  inte från förslaget), så "tomt akterut, tillbaka till kursen" kom aldrig och farten blev 4 kn. Nu räknas tiden
  från förslaget; väljer kaptenen en annan kurs föreslår sonar den gamla farten (`sonar.baffles.speed`); kontakter
  sonar redan kände, handel och övningsfartyget räknas inte som "hört något akterut".

**Buggar som hittades på vägen** (med oraklet och `skillnad.py`):
- Navigatören såg kortet framåt med bestickets osäkerhet åt sidorna men inte framåt: ja-boten gick på grund mot en
  brant strand i Clyde 0,25 nm från besticket. Nu `chart_ahead` med σ framåt.
- Pingpong: navigatören föreslog fix på periskopdjup, vakthavande "radarn mycket stark, djup 50", om och om igen.
  Vakthavande säger nu nej till periskopdjup under en mycket stark radar (`_radar_sees_masts`), navigatören tar
  bottenfixen i stället, och hans två fixförslag har en spärr. Vakthavande föreslår inte samma djup två gånger
  samma sekund (flyg- och fartygsradar).
- Övningen: navigatören föreslog farleden och vakthavande "kurs mot övningsområdet" om vartannat; nu inget
  farledsförslag på sista benet när farleden leder till ett känt mål, och inget områdesförslag när vi styr dit.
- Arktis: "stoppa här" vid stationen i en råk navigatören just sagt var för smal, om och om igen; och vaken till nyis
  kortare än båten (går inte att bryta igenom). Båda borta (`_narrow_at_station`, `IceMap.best`).
- Testet att ja-boten når drivstationen i minst 5 av 8 frön föll på brus: på 16 frön når båda versionerna
  stationen i 11 (gränsen nu 3 av 8).

**Kalibreringen** (ny baslinje, med utfall per frö och 16 frön i Clyde, Clyde-in, konvoj, konvoj-kort och krig-kort):
ja-boten i clyde-in inspelad 3 av 8 ⇒ 11 av 16, krig hemma 5 ⇒ 8 och förlorad 2 ⇒ 0, arktis stationen median 270 ⇒
179 min, jagad förlorad median 49 ⇒ 64 min; övrigt som förut. Clyde 3–4 av 16 klara med och utan sektorn (brus).
Oraklet (ja-boten, alla scenarier, 8 frön): tjat 25 ⇒ 7, skjutläge för djupt 13 ⇒ 0 (larmet räknar nu förslaget),
låg fart kvar 4 ⇒ 0; kvar säker men fel på övningens bevakningsfartyg (TODO).

**Verktygen** (`kalibrering/README.md`, Buggjakt): `skillnad.py` (första rapport som skiljer mellan arbetskopian och
en commit, `spela.py`), `kontroll.py` med utfall per frö, baslinjens commit och 16 frön där slumpen avgör
(`FLER_FRÖN`), `orakel.py` (larm mot sanningen) och `skytt.py` (ja, skjut, lyssna, JSON-loggar) med `sok.py`.

## 2026-11-23 – Minören föreslår den trådstyrda 53-62T

De två 53-62T låg i reserven i alla scenarier utom Övningen men laddades aldrig av sig själv: minörens förslag
tog bara SET-53 och 53-61. Nu föreslår han en 53-62T när ingen tub har eller laddar en ("den trådstyrda: sju
sjömil, och vi styr den mot plottets lösning tills målsökaren tar över"), annars som förut; salvan får 53-61
(`TorpedoRoom._reload_offer`). Lyssnande skyttebot, 11 krigs- och krisscenarier × 8 frön: 5 skott med 53-62T,
ytmål sänkta 9 av 15 skott (förut 5 av 13).

## 2026-11-23 – Långt skott: torpedrummet föreslår anfall, navigatören skjutdjup

Skyttebotens andra körning: 38 skott mot jagare, transporter och tankfartyg på säkra lösningar, inget sänkt;
median 5 nm och 4–10 min gångtid, målet girade under gången i 30 av 34 missar. Nu frågar torpedrummet en gång
före ett skott med en rak torped och gångtid över 5 min ("På den tiden hinner den gira eller ändra fart …
Upprepa ordern om vi ska skjuta ändå", `torp.long_shot`) och föreslår `anfall S-x` (`torp.suggest.close`) när
navigatören hinner till skjutläget och de inte har oss, och inte när vi redan anfaller målet eller dess konvoj
(`FiringMixin._long_shot`, `_can_close`). Målsökarna frågas inte (de söker efter giren). Framme i skjutläget
djupare än 100 m föreslår navigatören också skjutdjup (`fart 3, djup 90`, `ATTACK_DEPTH_MARGIN_M`): förut sa han
"vi är i skjutläge" på 220 m och föreslog bara fart 3. En bot som lyssnar (avstår vid frågan, säger ja till
anfallet, skjuter på god lösning i skjutläget), konvoj/krig/kuba/duell × 8 frön: 13 skott, 5 sänkta (förut 0 av 38).

## 2026-11-23 – Utredningarna efter skyttebotens körning, och beslutet i hytten

- **Säkra lösningar som inte satt sig.** Plottet kallade en lösning säker strax efter att den hoppat (kuba-kort 5:
  god 6,2 nm ⇒ säker 4,4 nm på 90 s, sanningen 6,3 nm och kursen 148° fel) och strax efter en lång lucka i
  bäringarna (krig 2). Mätning (ja-boten, 7 scenarier × 8 frön): efter ett hopp > 1σ var säkra grovt fel i 13 %
  (annars 1,2 %), goda i 33 % (6 %). Nu ett steg lägre i 2 min efter ett hopp och i 5 min efter en lucka > 10 min
  (`Knowledge._settled`, kunskap; `tma.solve` orörd). `tma_kvalitet.py` övning/kuba/konvoj-kort/sundet/krig-kort:
  frön 1–8 säker grova 1,1 % ⇒ 0,5 %, god 5,8 % ⇒ 2,8 %; frön 9–16 säker 2,4 % ⇒ 0,2 %, god 6,5 % ⇒ 4,7 %;
  ~10 % färre säkra, osäker 20 % som förut.
- **Målsökaren tar en neutral bortom målet.** Varningen gäller nu också kända handelsfartyg inom 1 nm från den
  målsökandes bana hela vägen ut (`SEEKER_LANE_NM`, `_lane_ships`); i konvoj-kort 1 varnar torpedrummet nu för S-2.
- **Varningen för en annan neutral räknades som bekräftelse av målet** utan att säga vad målet är: nu säger den
  det ("Och S-7 själv är inte säkert klassad som örlogsfartyg, bara …").
- **Lång gångtid.** Bara 7 av 65 skott med ≥ 4 min gångtid fick en varning (den krävde känd girrytm); nu varnar
  torpedrummet för gångtid över 5 min mot alla mål (`LONG_RUN_S`).
- **Småsaker:** ett köat "skjutlösning på S-x" från före skottet släpps när vi skjuter (`ReportQueue.drop`);
  kontakter som tappas inom 5 s sägs på en rad (`sonar.lost.many`). Navigatörens upprepade kvittens av ett djup
  som redan gäller får vara: en upprepad order upprepas tillbaka.
- **Hytten.** Förslaget starpom ringer om syntes bara som en rad längst ned, och skälen inte alls (hytten visar
  bara starpoms rader, och han sa bara "Radio föreslår sänd rapport. Det beslutet är ert."). Nu: en lapp
  nederst i bilden medan det ringer ("Enter svarar"), och sedan kortet ERT BESLUT mitt i bilden med vem som
  föreslår vad, stationens egna ord och "Skriv ja … nej …, sedan Enter"; starpom läser upp stationens ord i
  telefonen (`ui/cabin_render._decision_card`, `StatusSnapshot.decision_why`, `starpom.suggestion_why`).

## 2026-11-23 – Skyttebotens fynd: vapen i fredstid, salvan, omladdningen

En skyttebot (ja-boten som skjuter `eld`/`salva` på varje säker lösning) spelade alla 22 scenarier × 8 frön.
Det som rättades:
- **Fredstid.** Torpedrummet sköt mot en amerikansk jagare i Kuba utan att fråga (örlogsfartyg frågas aldrig),
  och i Clyde sänktes Polarisbåten utan att något hände: världen avslutar bara när *alla* fiender är sänkta.
  Nu frågar torpedrummet en gång före varje skarpt skott när ordern inte säger krig och vi inte angrips med
  skarpa vapen (`FiringMixin._weapons_hold`, `confirm_once`, kunskap: `Knowledge.at_war`, `war.assess`), och
  målet `PeaceBroken` (`Game` lägger det i scenarier utan `at_war`) avslutar med `peace_broken` när den första
  fienden sjunkit. Är det den sista gäller scenariots `sank`. I testerna är frågan av (fixturen `weapons_free`,
  `@pytest.mark.weapons_hold` slår på den).
- **Salvan.** Med bara en rak tub laddad sa torpedrummet "1 torpeder i solfjäder"; nu blir det ett vanligt skott
  (`torp.salvo_single`) med alla enkelskottets frågor. Salvan frågade inte heller om träffpunkten innanför
  armeringssträckan (`_too_close`, nu gemensam).
- **Omladdningen.** Förslaget kom bara vid tio minuters tystnad och aldrig under jakt; i krig-kort stod tuberna
  tomma i två timmar och torpedrummet sa nej 20–50 gånger. Nu föreslår minören omladdning en minut efter skottet
  (inte medan de har oss, `RELOAD_SUGGEST_S`, igen efter 10 min) och genast när ett skott nekas för att ingen tub
  kan (`_suggest_reload(urgent=True)`).

Skotten (före rättelserna): 33 skott på säkra lösningar, 3 träffar, alla på Polarisbåten i ytläge; 0 av 26 mot
jagare, transporter och tankfartyg (median 4,6 nm, målen girade under gången). Kvar i `docs/TODO.md`.

## 2026-11-23 – Svansen (`svansen-kort`) och sonarns döda sektor

Nytt kort krigsscenario, ~20 min: natt i Norska havet, vi går i 10 kn och en amerikansk Skate skuggar oss i
döda sektorn akterut. Sonar föreslår efter tio minuter rakt en gir och fart 4 för att lyssna i kölvattnet och
säger till om det är tomt; ubåten märker vår fartändring sent och kommer då fram. Sänk den eller skaka av den
(ingen har haft oss på 10 min). Den skjuter när den har sin lösning (12–16 min) eller när vi röjt att vi har den.
Var det bor: `sim/scenario/svansen.py`, döda sektorn `OwnShip.baffle_deg` och `sim/sonar.py` `baffle_loss`
(bara Svansen; idén att införa den överallt i `docs/IDEER.md`), sonarrummets gir `sim/stations/baffles.py`,
skuggningen `SubmarineAI.state = "shadow"` (`sim/arctic.py`), målet `ShakeGoal`. Kalibrering: första rapport
~130 s, ja-boten skakar av 3 av 8, passiv förlorad 5 av 8.

På vägen: utan fart 4 i giren hördes ubåten aldrig (vårt eget brus i 10 kn dränkte den även på sidan), och
sonars utlåtande räknade först varje gir som en lyssning, tog kursen mitt i giren och sa "tomt" fast en kontakt
hörts under lyssningen; nu gäller utlåtandet bara sonars egen gir, kursen tas när giren är klar och varje ny
kontakt under lyssningen räknas.

## 2026-11-23 – Torpeden i vattnet (`duell-torped`) och sammansatta förslag

Ny kort variant i Duellen, ~15 min: den amerikanska ubåten har sin lösning klar och öppnar torpedrören några
sekunder efter att kaptenen tagit befälet; en Mk 37 är i vattnet en halv minut senare, 3–3,5 nm bort. Undan
först, sedan sänk den eller ta er ut. `SubmarineAI.opening_shot_t` (skjuter på lösningen den har, vad den än
hör), `duel_torpedo_scenario`. Kalibrering: passiv förlorad 8 av 8, ja-boten överlever 8, undan 2.

Fel som hittades på vägen: ett sammansatt förslag ("kurs 189, fart 28, djup 234", sonars undanmanöver) tolkades
som en okänd order och släpptes aldrig som redundant, så sonar kunde föreslå samma undanmanöver igen fast allt
redan var beordrat. Nu är det avgjort när varje del är det (`Game.suggestion_redundant`, `_order_decided`).
duell-kort med ja-boten oförändrad. Det förde fram ett äldre fel: en bestående order räknades som gällande
bara för att kaptenen senast gett den, fast ett uppdrag (vaken, styrningen) sedan ändrat fart eller kurs; i
Arktis släpptes då navigatörens "fart 5, djup 60" för att återuppta sökningen (ja-boten nådde öppet vatten i 6
av 8 frön i stället för 8). Nu frågar Game stationerna (`Station.order_in_force`; navigatören svarar för kurs,
fart och djup ur rodren och maskinen).

## 2026-11-23 – huvudmenyn i avdelningar

Uppdragen står i tre avdelningar: ÖVNING, KRISEN (fred, förbli oupptäckt) och KRIGET (vapen fria), med en röd
avdelningsrad i listan; beskrivningen säger avdelningen ("Kriget: vapen fria"). `ScenarioDef.section`
(standard krisen), `SECTIONS` och `section_label` i `ui/menu.py`; `FIRST_GROUPS` är borta. Ett uppdrag får
vara bara kort (förberett för Svansen).

## 2026-11-23 – torpederna på vattenfallet

Sonar hörde torpeder med bäring men ritade dem aldrig: nu står de på vattenfallet. En fientlig torped som
`torped 1` i egen färg över allt annat (bäringen som står still syns), våra egna som `tub 2`, dämpade; etiketten
dämpas när sonar tappat dem. Fientliga ur sonarrummets bäringar (`IncomingMixin.torpedo_traces`), egna ur
torpedrummet (`Running.heard`, `OwnTorpedoHeard.se`), ritade i `ui/sonar_render.py` (`TorpedoTrace`).

## 2026-11-22 – skjutlösningen bara för torpeder ombord

Skjutlösningen räknade kurs och gångtid för alla torpedtyper i spelet, så övningstorpeden stod med i varje
scenario fast den bara finns ombord i övningen. Nu räknar torpedrummet bara på typerna i tuberna eller i stället
(`FiringMixin._aboard`, `firing.py`). Test: `test_the_solution_lists_only_torpedoes_aboard`.

## 2026-11-22 – appens standardmål ~/Applications

Ingen ändring i spel. `ikon/bygg-app.sh` bygger `K-114.app` till `~/Applications` om inget mål anges, i stället
för mappen `~/Projekt/Lokalt` som bara fanns på en dator. README säger inte längre att appen är avinstallerad.

## 2026-11-22 – plottets kurs: en osedd gir hos mål som girar ofta

Provskjutningen visade att plottets säkra lösningar hade kursen fel med mer än 3σ i 18 % av fallen på mål i rörelse.
Mätningen (säkra och goda lösningar mot sanningen, 80 spel): felen satt där målet girat de senaste 5 minuterna (39 %
utanför 3σ, mot 4 % efter 20 min) och hos mål som plottet vet sicksackar (28 %). En gir syns inte i bäringarna
förrän efter några minuter, så den går inte att upptäcka tidigare; att skala osäkerheten med anpassningen eller
pröva anpassningen på de senaste minuterna hjälpte knappt. Nu räknar `tma.solve` för mål med q ≥
`ZIGZAG_MANEUVER_Q` (sicksack, jagare som jagar) med en gir som kan ha skett de senaste 3 minuterna utan att synas
(`RECENT_TURN_S`, `ZIGZAG_LEG_S` 7,5 min, `ZIGZAG_TURN_DEG` 50°), kortat till tiden sedan senaste titten som visade
kursen (periskop, brygga). I spel: konvojfartyg och sicksackande jagare blir säkra bara strax efter en periskoptitt,
annars som bäst goda. Periskopet blir vägen till ett säkert skott mot konvojen.

Mätt: säkra lösningar på sicksackande mål med kurs > 3σ 28 % ⇒ 6 % (antalet säkra där 185 ⇒ 17, goda kvar); alla
säkra 10 % ⇒ 5 %. `tma_kvalitet.py` (övning, kuba, konvoj-kort, sundet, krig-kort, 8 frön): säker grova 1,7 % ⇒ 1,1 %,
> 3σ 5,1 % ⇒ 5,7 %, god grova 5,3 % ⇒ 5,8 %. Provskjutningen (kuba, konvoj-kort, konvoj-mot, sundet-in, krig-kort,
frön 1–8): 53-61 på säkra lösningar 38 % ⇒ 42 % träff, kurs > 3σ 15 % ⇒ 11 %. `kontroll.py`: som baslinjen.

## 2026-11-22 – målsökaren kan ta fel fartyg: torpedrummet varnar

Varningen för handelsfartyg nära banan gällde bara raka torpeder. En målsökande tar det den hör bäst, och i
provskjutningen tog SET-53 ett annat fartyg i 19 av 148 skott (i sundet oftast patrullbåten). Nu varnar
torpedrummet före skottet med en målsökande torped (SET-53, 53-62T) när ett annat känt fartyg (inte egna
örlogsfartyg) enligt plottet ligger inom 0,6 nm från målet när torpeden är framme, eller utan lösning i bäring
inom 10° från kursen (`FiringMixin._seeker_rivals`, `RIVAL_NM`): "S-2 (patrullbåt, bäring 005, 2,0 sjömil) ligger
nära S-1 när den målsökande torpeden är framme. Målsökaren tar det den hör bäst och kan ta fel fartyg. Upprepa
ordern om vi ska skjuta." Samma fråga en gång som för handelsfartygen; `skjutlösning` säger det när en
målsökande torped är laddad.

## 2026-11-22 – anläggningsvinkeln i skjutlösningen

`skjutlösning S-1` säger nu varifrån den raka torpeden kommer in: "Den raka torpeden kommer in 10° från aktern,
styrbord: målet är smalt härifrån och en salva hjälper inte, bättre läge från sidan." (`FiringMixin._aspect`,
`torp.solution` `aspect`). Bara när målet går minst 2 kn och plottets kurs-σ är under 30° (`ASPECT_MIN_KN`,
`ASPECT_MAX_SIGMA`); smalt inom 25° från stäv eller akter (`NARROW_DEG`). I provskjutningen träffade 48 % av skotten
0–20° från för eller akter mot 60 % från sidan med samma sikte.

## 2026-11-22 – benvarningen för alla mål som girar

Torpedrummets varning för att målet kan gira innan torpeden är framme gällde bara konvojens fartyg. I
provskjutningen träffades jagare 1 gång av 84 med 53-61, eftersom de girade under gången. Nu varnar det också för
mål med två märkta girar (benlängden ur plottets girar, `FiringMixin._turn_rhythm`) och för en jagare som jagar
oss (`Knowledge.hunting`, utbruten ur `resolve`): "S-2 jagar och girar hela tiden, och en 53-61 är framme om
5 min 10 s. Den hinner gira. En målsökande torped har större chans." Gångtid under 2 min ger ingen varning
(`HUNTING_RUN_S`). Varningen är aldrig ett förslag att skjuta.

## 2026-11-22 – rapporten säger sänkt, inte träff

Rapporten till staben tog med "TORPEDTRÄFF HÖRD" efter varje detonation av en egen torped, också en som gått av
i förtid eller på grund. Nu räknar radion det sonar hör sjunka (`ContactSunk`, brytningsljudet) och skriver
"FARTYG SÄNKT, BRYTNINGSLJUD HÖRT" (`radio/station.py`, `dispatch.EVENT_TEXT`).

## 2026-11-22 – provskjutning på säkra lösningar: torpederna går på grund, djupet och för tidiga detonationer

En timmes provskjutningar (`kalibrering/skott_saker.py`, nytt: ja-boten spelar, och vid varje säker lösning
spelas fröet om och kaptenen skjuter) gav fyra buggar, rättade här:

- **Torpederna gick genom land.** En 53-61 mot land i Clyde gick 223 s över land och vidare. Nu går alla
  torpeder på grund där botten är mer än 1 m grundare än deras djup (`weapons._ground`, `GROUND_MARGIN_M`);
  en armerad stridsspets detonerar där, en oarmerad, blindgångare eller övningstorped stannar bara.
- **Raka torpeder sänkte ubåtar på djupet.** Egna torpeder träffar nu bara inom `DEPTH_HIT_M` (20 m) i djup,
  som fiendens redan gjorde: 53-61 på 5 m går över amerikanska ubåten på 150 m i duellen. Målsökarna (SET-53,
  53-62T med målsökaren släppt) styr i djup mot det de låst på (`_seek`), aldrig grundare än sitt gångdjup.
- **En gammal "säker" lösning när en kontakt återfanns.** Knowledge behöll lösningen medan kontakten var tappad;
  när sonar fick tillbaka den visade sjökortet i upp till 30 s (till plottets nästa omräkning) en lösning från när
  den tappades (i kuba frö 21: 55 min gammal, 13 nm fel, "S-3 säker, 14 kn"). Nu kastas den när en tappad
  kontakt återfinns (`Knowledge.on_detection`); plottet räknar om ur bäringarna.
- **En förtidsdetonation kallades träff.** En detonation mer än 30 s och en fjärdedel av gångtiden före beräknad
  träfftid ger nu "Tub 1: detonation i bäring 012, 2 min 20 s före beräknad tid. Den har inte nått S-1: den gick
  av i förtid eller tog något annat." (`torp.run.early`, `EARLY_MIN_S`, `EARLY_FRACTION`) i stället för
  `torp.run.hit`. Samma sak när torpeden går på grund före målet.

Provskjutningen före rättelserna (986 skott, 9 scenarier, 32 frön) står i `kalibrering/README.md`.
`kontroll.py` efter rättelserna: som baslinjen.

## 2026-11-22 – webbversionen först i README

README börjar med "Spela": länken till GitHub Pages, ljud med `ljud`, tangenterna i webbläsaren, skärmstorlek
och `?scenario=`/`&seed=` med alla scenarier. Nedladdat (`uv run main.py`, `fonster.py`) står under "Spela utan
webbläsare" som reserv, med `git clone` och uv; testerna och bygget av webben under "Utveckling". `web/README.md`
hänvisar spelare till sidan och `CLAUDE.md` säger att det ska förbli så.

## 2026-11-22 – stilla fartyg hörs mindre

Ett fartyg som ligger still eller glider under 3 kn har bara hjälpmaskinerna igång: källnivån faller linjärt
till 12 dB under framdrivningens vid stopp (`acoustics.source_level`, `IDLE_KN`, `IDLE_DB`; ankrade `moored`
som förut). En stoppad jagare är 125 dB i stället för 137, så sonar hör den kortare och en jagare som stannar
för att lyssna blir svårare att hålla kvar. Målsökarna träffar som förut inom 3 nm men sämre längre ut (53-62T
på 5–6 nm 20–22 ⇒ 14–16 av 24). `kontroll.py`: som baslinjen.

## 2026-11-22 – torpedfel och skrovets ellips

Egna torpeder är inte längre perfekta (`sim/weapons.py`). Gyrot lägger torpeden på kursen med ett fel σ 0,4°
(`GYRO_SIGMA_DEG`, ~40 m vid sidan på 3 nm), var tjugonde stridsspets klickar (`DUD_P`) och var femtionde
går av för tidigt efter armeringen (`PREMATURE_P`); övningstorpeden och kärnladdningen har inga sådana fel.
En blindgångare slår i skrovet med en smäll (`acoustics.DUD_LEVEL` 150 dB, transient `dud`); sonar hör den
och torpedrummet säger "Blindgångare, kapten. Målet är kvar" (`torp.run.dud`). En förtidsdetonation hörs som
en vanlig detonation, men inget brytningsljud följer. Träffytan är skrovets ellips (`HULL_M`, `hull_pass`):
halva längden och bredden per typ plus 10 m, så ett skott rakt för- eller akterifrån måste ligga nästan
mitt på. Övningens "under kölen" räknas likadant. Fiendens Mk 37 mot oss har kvar cirkeln. Provskjutningen
(24 frön): en ensam 53-61 22/18/6/9/1/1 av 24 på 1–6 nm (förut 24/24/10/13/5/3), salvan 15/24 på 3 nm,
målsökarna missar bara på felen. Tester som prövar geometri och rapporter stänger av felen med fixturen
`perfect_torpedoes`; felen prövas i `tests/test_torpedo_faults.py`.

## 2026-11-22 – provskjutningen med eget frö per avstånd

`kalibrering/ytskott.py` ger varje frö och avstånd ett eget spelfrö (`run_seed`) och visar andelen träffar
med 90 % konfidensintervall; standard 24 frön. Förut gav samma frö samma sensorslump och bäring på alla
avstånd, så 48 skott var 8 försök. Nu: en ensam 53-61 träffar 24/24 till 2 nm, 10–13 av 24 på 3–4 nm, 3–5
på 5–6 nm; salvan 19/24 till 4 nm. Ändrar inte spelet.

## 2026-11-21 – CI kör alla tester vid push

`.github/workflows/tester.yml` kör nu `uv run pytest -q --slow` vid varje push till main, inte bara vid
pull request och för hand. Förut hade de 98 långsamma testerna (hela spel, statistik över frön) aldrig
körts i CI, eftersom allt committas direkt på main. Repot är offentligt, så minuterna är gratis.

## 2026-11-21 – testerna rensade från överlapp

Ingen exakt dubblett bland de 1 046 testerna (samma namn i samma fil, samma kropp eller > 90 % lika).
Två överlapp rättade: det långsamma `test_game.py::test_reports_never_reveal_truth_ids` letade bara
efter `DD1` och prövar nu alla sanningens id:n med samma mönster som torpedtestet (döpt om till
`test_torpedo_reports_never_reveal_truth_ids`); `test_menu_audio.py` prövade inte längre `read_wav`, som
bara skickar vidare till `voices.read_wav` (prövas i `test_voices.py`). Noterat: CI har bara kört de
snabba testerna (alla körningar vid push); `--slow` körs bara lokalt.

## 2026-11-21 – ikonen i Safari

Webbsidan länkade bara ikonen i 1024 px utan storlek, och Safari visade ingen. Nu finns en flikikon i
32 px och en `apple-touch-icon` i 180 px (Safaris favoriter och startsida) bredvid den stora, med
storlekar i `web/index.html`. Filerna `ikon/k114-32.png` och `ikon/k114-180.png` görs av
`ikon/bygg.py` (`WEB_SIZES`) och kopieras av `web/bygg.py` (`ICON_SIZES`); `tests/test_webb.py`
kollar att varje länkad ikon finns i bygget.

## 2026-11-21 – webbversionen varnar på telefoner

På en liten skärm (terminalen under 100×30 tecken) eller en pekskärm utan mus säger sidan, innan den
laddar Pyodide, att K-114 är ett textspel för dator. Står telefonen upp ber den om liggande läge, och den
påminner om att vyerna nås med ord (`sjökort`, `sonar`, `ubåt`, `logg`, `central` tillbaka) eftersom
telefonens tangentbord saknar Tab och Esc. Spelet vägrar aldrig: "Spela ändå" startar det och valet
sparas i webbläsaren. Bara `web/index.html` (`mobileWarning`); provat i panelen i mobil- och datorstorlek.

## 2026-11-21 – K-114.app raderad

Appen i `~/Projekt/Lokalt` är borttagen; spelet startas med `uv run main.py`, `fonster.py` eller i
webbläsaren. Inget gick förlorat: appen var bara länkar och ett startskript, och ikonen (`ikon/K-114.icns`,
`k114.svg`, PNG-filerna) finns i repot. `sh ikon/bygg-app.sh` bygger den igen.

## 2026-11-21 – utrett: konvoj-kort och ja-boten efter rättelserna

Ingen försämring. Ja-boten skjuter aldrig i konvoj-kort (avfyring föreslås aldrig som ja-order), så
`convoy_missed` där betyder att konvojen passerade utan skott, inte en missad salva. Att det blev 3 av 8
i stället för 0–1 kommer av färre sprintförslag efter rättelserna: boten jagar inte ikapp konvojen, som
hinner 8 nm bort före tidsgränsen. Siffrorna i `kalibrering/README.md`.

## 2026-11-21 – ljud i webbversionen, W3: inkopplat

Webbversionen har ljud: `ljud` (eller Inställningar) slår på bakgrunden, larmen, hydrofonljuden och talet,
och menyns musik och hamn. `ui/audio.py`: `make_soundboard` bygger i webbläsaren en `WebPlayer` (ljuden i
mixern, talet direkt med `voices.WebSpeech`, inga trådar) och `sound_available()` ersätter
`MacPlayer.available()` i appen och inställningarna. Ljudutgången väljs med `ambience.output()`
(`OUTPUT`, som `web/start.py` sätter till `WebOut`), så `ui/` känner inte `web/`. `MenuSound` körs utan tråd
(`threaded=THREADS`); syntesen låser sidan ~1 s när ljudet slås på i menyn. Provat i panelen: övning-kort
med reaktor, turbin, kontakterna S-1 och S-2 och ryskt tal; menyn med musik och hamn; inga fel i konsolen.

## 2026-11-21 – ljud i webbversionen, W2: talet

`ui/voices.py` har en tredje backend, `WebSpeech`, som `backend()` väljer under Pyodide: den läser upp
med webbläsarens `speechSynthesis` genom sidans brygga (`makeSpeech` i `web/index.html`). Spelets
röstnamn behålls (Alva, Milena); sidan tar den rösten om webbläsaren har den, annars en annan på samma
språk. `render` ger None, så telefon- och skotteffekten och Radio Moskva hörs inte i webben. Chrome kan
tappa en replik utan `onend`: sidan håller kvar replikerna och räknar dem som slut efter en generös gräns,
så att besättningen aldrig fastnar. Provat i panelen (Chromium på Mac): Alva och Milena hittas och en
replik läses upp och tar slut. Ännu inte inkopplat i spelet (W3).

## 2026-11-21 – ljud i webbversionen, W1: utgången

Mixern (`ui.ambience.Ambience`) kan spela i webbläsaren. `web/web_audio.py` (`WebOut`, samma gränssnitt
som `AmbientOut`) fyller från händelseslingan på en kö 0,25 s fram, eftersom Pyodide saknar trådar och
Web Audios ljudtråd inte kan anropa Python; en AudioWorklet i `web/index.html` spelar kön i 22 050 Hz.
Står slingan still längre än kön räcker blir det tyst en stund och kön börjar om. Ännu inte inkopplat i
spelet (W3). Mätt i Pyodide: ~0,3 ms per block om 46 ms, syntesen av bakgrundsljuden 0,2 s, menyns 1 s.
Provat i panelen: ljudklockan går efter ett klick och kön hålls vid 0,25 s. Tester med låtsad sida i
`tests/test_webb.py`.

## 2026-11-21 – webbversionen (GitHub Pages)

Spelet går att spela i webbläsaren, utan ljud. Pyodide kör samma `sim/` och `ui/`, och Textual ritar i
xterm.js genom en egen drivrutin (`web/pyodide_driver.py`: escapesekvenserna till terminalen i sidan,
tangenter och storlek tillbaka på samma händelseslinga, inga trådar). `web/bygg.py` packar spelet bredvid
`web/index.html`; `.github/workflows/pages.yml` publicerar när det körs för hand (inte vid push). Publicerad 2026-11-21 på
https://thohig.github.io/silent-service-txt/ (repot gjort offentligt, kuba-kort provat där). Pyodide saknar trådar, så en
kort variants uppvärmning körs i bitar mellan ritningarna (`Game.warm_up_steps`, samma spel som `warm_up`,
testat). Provat i Chromium: menyn, övning i övningsområdet (uppvärmning, order, förslag, vyerna med Tab).
Simuleringen går 1–2 gånger långsammare än i CPython (övning ~8 ms per tick mot ~4, konvoj och krig < 1 ms).
Lapp: Pyodide 0.29:s `WebLoop.create_task` anropar `asyncio.tasks._set_task_name`, som saknas i Python 3.13.

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
- **Fråga en gång** (`Station.confirm_once` i `intercept`, `CONFIRM_S` 60 s): navigatören om dykning i
  fjorden och om ytläge när plottet har en fiende inom 6 nm (`SURFACE_THREAT_NM`), maskin om
  nödblåsning utan vatten i båten eller djupfara. Upprepad order verkställs; ett förslag kaptenen sagt
  ja till (`Game.accepting`) och vakten före överlämnandet (`Game.warmup_running`) frågas aldrig.
  Förut: `djup 100` i fjorden ⇒ misslyckad övning efter 0 min, nödblåsning under jakt ⇒ tvingade upp.
- **En minut i ytläge:** `World._check_outcome` slutar med `forced` först när fienden sett oss i
  `SURFACE_GRACE_S` (60 s); utkiken hinner ropa och vi hinner dyka.
- **konvoj-mot:** vaktens salva upprepades blint och sköt rakt igenom torpedrummets varning för ett
  neutralt fartyg i banan (neutral sänkt efter 3 och 9 min i 2 av 24 frön). Nu byter vakten mål.
  24 frön, passiv kapten: anfallen 9, tiden ute 13, förlorad 1, missad 1 (förut neutral sänkt 2).
- **Radarvarnaren** ropar ut samma radar igen bara när styrkan ändrats, den flyttat sig mer än 15° eller
  efter 30 min (`ESM_REPEAT_S`, förut 10); kommer vi upp och bara känner igen dem säger den "samma tre
  radarstationer som förut" (`off.esm.same`). Clyde frö 29: 9 rader på 2 h i stället för 39.
- **För nära för att skjuta:** ligger träffpunkten närmare än armeringssträckan + 0,15 nm frågar
  torpedrummet en gång ("exploderar inte", `torp.too_close`); boten sköt förut på 0,3 nm utan ett ord.
- **Botten under anfall:** navigatören föreslår inte botten när skarpa sjunkbomber fallit nära de
  senaste 5 min (`Knowledge.charged_close`), och ligger vi på botten när de bombar oss där föreslår
  maskin att lätta (`eng.suggest.lift`: turbin och sprintfart). Kalibreringskontrollen visade det:
  ja-boten i krig la sig på botten mitt i anfallet och dog där (2 av 8 förlorade).
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
