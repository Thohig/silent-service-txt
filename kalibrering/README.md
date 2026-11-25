# Kalibreringsbotar

Huvudlösa genomspelningar som ger siffrorna under Siffrorna nedan (förut i CLAUDE.md). De är inga tester.
De körs för hand från repots rot efter en medveten ändring av kalibreringen:

```bash
uv run python kalibrering/ja_bot.py ovning-kort,konvoj-kort 8
```

Varje skript beskriver sina argument överst i filen. Botarna är flyttade hit som de var i
scratchpad (2026-11-14–15). En del läser sanningen (`sundet.py --orakel`, `sundet_folj.py` utan
`--följ`). Sådana värden mäter bara scenariot, inte vad besättningen klarar.

**Buggjakt (2026-11-23).** Ordningen när något ändrats: `kontroll.py` (flyttat? vilka frön?), sedan
`skillnad.py` på ett frö som bytt utfall (första rapport som skiljer mot baslinjens commit), och
`skytt.py` i alla tre lägena för larmen (oraklet). `sok.py` söker i skytt-loggarna.

```bash
PYTHONHASHSEED=0 uv run python kalibrering/kontroll.py
uv run python kalibrering/skillnad.py clyde 15 --mot 09baead
PYTHONHASHSEED=0 uv run python kalibrering/skytt.py lyssna alla 0-7 180
uv run python kalibrering/sok.py lyssna --larm
```

| Skript | Scenario | Botar |
|---|---|---|
| `kontroll.py` (också i Actions: `kalibrering.yml`, söndagar och för hand) | alla | passiv och ja-boten, 8 frön (16 där slumpen avgör, `FLER_FRÖN`), mot `baslinje.json` (`--spara` skriver den, med commit och utfall per frö); listar fröna som bytt utfall och kommandot för `skillnad.py` |
| `skillnad.py` | ett scenario, ett frö, `--mot COMMIT`, `--bot`, `--minuter`, `--sammanhang` | samma frö med arbetskopian och en äldre commit (utpackad i `logs/skillnad/`); första rapport som skiljer, med sammanhang från båda. `spela.py` spelar och skriver flödet som JSON |
| `skytt.py` | läge (`ja`, `skjut`, `lyssna`), scenarier eller `alla`, frön, minuter | ja-boten, skyttebot (eld/salva på säkra lösningar, går förbi frågorna) och lyssnande skyttebot (avstår vid långt skott, tar anfallet, skjuter på god i skjutläget); oraklet (`orakel.py`) larmar för grund utan varning, skjutläge för djupt, tjat, låg fart kvar, säker men fel, neutral utan varning, textfel, undantag; flödet som JSON till `logs/skytt/<läge>/` |
| `sok.py` | läge, `--typ`, `--text`, `--roll`, `--scenario`, `--antal`, `--visa`, `--larm` | söker i skytt-loggarna |
| `fingeravtryck.py` | alla | ja-boten, hash av rapporter, läge och vyer: samma frö ⇒ samma spel (omstruktureringar) |
| `ja_bot.py` | alla (kommaseparerade) | ja-boten, parallellt |
| `duell.py` | duell, duell-kort, duell-torped, svansen-kort | passiv, ja, verktyg (ja + målsökande torpeder) |
| `ovning.py` | ovning | ja-boten: tid, grund, bestickfel |
| `ovning_lyssna.py` | ovning | lyssningens längd, partnerns svar |
| `ovning_torped.py` | ovning, ovning-kort | ja + skjuter övningstorped |
| `jagad.py` | jagad (`--scen=` annat) | ja, `--passiv`, `--taktisk`, `--sprint` |
| `jagad_djupt.py` | jagad | djupt och fort längs navigatörens väg ut |
| `jagad_kort.py` | jagad-kort | passiv, ja, fast |
| `kuba_kort.py` | kuba-kort | passiv, ja |
| `kuba_flyg.py` | kuba | ja; flygets och jagarens kontakter |
| `kuba_jakt.py` | kuba | ja över 12 frön: upptäckt, sjunkbomber |
| `sundet.py` | sundet | besättningens verktyg, `--ja`, `--orakel` |
| `sundet_folj.py` | sundet | grindtricket (`--följ` = besättningens verktyg) |
| `sundet_in.py` | sundet-in | passiv, ja, grind |
| `sundet_ut.py` | sundet-ut | passiv, ja, ut |
| `clyde.py` | clyde, clyde-in | passiv, ja, verktyg (över skiktet, följ Polarisbåten) |
| `konvoj.py` | konvoj | passiv, ja, attack |
| `konvoj_salva.py` | konvoj, konvoj-kort | ja + salva mot stora fartyg |
| `konvoj_mot.py` | konvoj-mot | passiv, ja, bort |
| `krig.py` | krig, krig-kort (första argumentet), botar, antal frön; `KRIG_VERBOSE=N` skriver de sista N rapporterna | passiv, ja, verktyg (ja på alla förslag, periskop var 4:e min, `anfall`, salva mot klassad transport/tanker ≤ 3 nm med god lösning, sedan djupt bort en kvart) |
| `arktis.py` | arktis | ja |
| `arktis_kort.py` | arktis-kort | passiv, ja |
| `tma_kvalitet.py` | flera | ja; plottets lösningar mot sanningen per kvalitet |
| `rad.py` | kuba, kuba-kort, jagad, jagad-kort (kommaseparerade) | hök-boten: ja-boten som laddar T-5, håller kärnvapenrådet vid varje bomb nära, går upp till skjutdjup och skjuter med nycklarna |
| `starpom.py` | kuba, konvoj (kommaseparerade), frön, ev. `salva` | kaptenen lämnar över och sover, går till centralen för sina beslut; med `salva` skjuter han där (som `konvoj_salva.py`); mot samma kapten utan starpom |
| `langvag.py` | scenarier (kommaseparerade), frön | ja-boten; radiogram med masten och på långvåg, stympade och missade sambandstillfällen |
| `ytskott.py` | (eget upplägg) typer, frön (24) | ytläge, stillaliggande jagare 1–6 nm, radar varje minut i 10 min, sedan ett skott (eller `salva`) per typ |
| `skott_saker.py` | scenarier, frön (1-16 eller 1,4,7), minuter, typer (53-61, SET-53, salva), max skott per spel | ja-boten; vid varje säker lösning (högst var 5:e min per kontakt) spelas fröet om och kaptenen skjuter; lösningens fel, siktfelet och utfallet. `PYTHONHASHSEED=0` |
| `provspel.py` | scenarier (kommaseparerade), timmar, frö | provspelskaptenen: ja, rutinorder, vyer, periskop, eld på god lösning ≤ 3 nm; hela rapportflödet till `logs/provspel/` att läsa |
| `kaos.py` | scenarier, frön (kommaseparerade), minuter | kaosboten: slumpade, udda och felaktiga order, ja/nej/jest på förslagen, vyer varje minut; letar undantag, oifyllda fält, punktdecimaler, kurser utan tre siffror, NaN, sanningens id:n; flödet till `logs/kaos/` |

Provkörda 2026-11-15 med ett frö var. Alla gick utan fel. `konvoj.py` och `kuba_jakt.py`
kördes bara 45 s utan fel, eftersom de har fasta frön och tar lång tid.

## Siffrorna

**Stampvinkeln (2026-11-24, baslinjens commit 70832d5):** `kontroll.py` (35 min): krig ja hemma 4 ⇒ 7 av 8 (frön 0, 4, 5;
förlorad median 513 ⇒ 337 min, ett frö), jagad ja undkom 6 ⇒ 7, duell ja undkom 3 som förut men median 54 ⇒ 93 min,
duell-kort ja förlorad 4 ⇒ 5 (3 i en körning med brant vinkel också uppåt: brus). Första versionen gick brant också uppåt:
konvoj-mot ja anfallet 4 ⇒ 2 (frö 0: uppåt mot periskopdjupet 21°, slammer, eskorten hörde oss och salvan kom aldrig
iväg; `skillnad.py konvoj-mot 0`); med brant bara nedåt 4 som förut. Baslinjen sparad (commit 3b5637c).

**Talnivån (2026-11-24):** ja-boten 2 h per spel, frön 0–3, kuba, konvoj-kort, jagad-kort, ovning, sundet, krig-kort
(2181 min, ett `SoundBoard` per nivå på samma spel, tecken i det som köas för uppläsning; loggen påverkas inte): allt 131 tecken/min och 115 repliker/h,
viktigt 76 och 65 (42 % mindre uppläst), larm 44 och 26; alla 935 larm och förslag på de tre nivåerna. Störst kvar på viktigt:
`plot.improved`, `plot.maneuver` (larm), `sonar.lost`, `sonar.classified`. Boten ger få order, så kvittenserna (som
blir "Есть") väger mer i riktigt spel. Mätskriptet låg i scratchpad (en `SoundBoard` per nivå i `LEVELS`).

**Utredningen av krig-kort och vaken under isen (2026-11-24, baslinjens commit 70832d5 för isen, c59554b för
resten):** krig-kort ja-boten frö för frö (`perseed`-skript i scratchpad med `kontroll.run`): 3c9ce48 10 av 32
hemma, d3d4621 5, c14e215 6; 12 frön bytte utfall åt båda håll, flödena skiljer sig efter några minuter (en rapport
1–2 s senare, `skillnad.py` frö 0 och 8). Frön 32–95: 3c9ce48 12, c14e215 14; över 96 frön 22 mot 20, slump.
`kontroll.py` alla scenarier: krig ja hemma 7 ⇒ 4 av 8 (frön åt båda håll; frö 4 förlorad på botten när reaktorn
snabbstoppat, nu lättar maskin på elmotorn men frö 4 förloras ändå). Vaken (mät upp råken, back till mitten, kort
nyis inte värd att backa till, öppningen isen drivit in över stryks): arktis ja stationen 5 ⇒ 7 av 8 (median 227 ⇒
252 min), arktis-kort 2 ⇒ 3; duell ja undan 5 ⇒ 3 av 8 (frön 0–7), men frön 8–23 9 ⇒ 8, över 24 frön 14 mot 11: slump.
Oraklet (`skytt.py ja alla 16-23`, 176 spel): ett larm, arktis 16 "vak" 4 gånger på 19 min när isen driver (fyra olika
lägen; förslag och order talar nu om samma öppning). `--slow` 1179 gick igenom.

**Provspelet i alla scenarier (2026-11-23 kväll, baslinjens commit cc8eb9e):** `skytt.py` ja/skjut/lyssna frön
8–15, `provspel.py` alla 22 scenarier (frö 31, 41, 51), `kaos.py` 88 spel utan undantag. Torpeden i döda sektorn
(larmet gäller 12 min): duell-kort ja förlorad 13 ⇒ 6 av 16 (60 min), Svansen-kort 3 ⇒ 2, jagad oförändrad; försök
utan döda sektorn för torpeder bara 13 ⇒ 11 (förslagen efteråt var det som dödade). TMA (`tma_kvalitet.py`):
ubåt i undervattensläge som sicksack, duell-kort god grova 69 % ⇒ 50 %, kurs > 90° 56 % ⇒ 17 % (12 frön, 60 min);
konvojens eskort som sicksack, konvoj/konvoj-kort/krig-kort/konvoj-mot god grova 7,3 % ⇒ 5,8 %, > 3σ 8,0 % ⇒ 7,0 %,
säkra grova på jagarna (skyttebot, 32 spel) 7 ⇒ 3; arktis, övning, Clyde-in oförändrade. Övningens bevakningsfartyg
(kursen ~100° fel med rätt avstånd) är minuten efter en gir på 130°, inte ett fel. `kontroll.py`: arktis ja stationen
3 ⇒ 6 av 8, duell-kort ja förlorad 6 ⇒ 4, konvoj-kort ja missad 4 ⇒ 1 av 16, duell ja ute 6 ⇒ 4 (ingen förlorad),
arktis-kort 3 ⇒ 2. Lyssningsgirens upptrappning: svansen-kort, clyde-in, ovning-kort oförändrade (16 frön).

**Rättelser efter provspelet (2026-11-21, `kontroll.py` frön 0–7):** jagad ja undan 5 ⇒ 7, förlorad 3 ⇒ 1
(median 74 ⇒ 49 min); jagad-kort ja undan 6 ⇒ 8; konvoj-mot ja anfallen 3 ⇒ 5; konvoj-kort ja konvojen
passerad 1 ⇒ 3 (tiden ute 7 ⇒ 5; ja-boten skjuter aldrig, se nedan); krig ja hemma 7, förlorad 1 (efter första omgången 2: båten la sig på botten
mitt i anfallet, nu `charged_close` och `eng.suggest.lift`). konvoj-mot passiv med vaktens salva, 24
frön: neutral sänkt 2 ⇒ 0. Baslinjen sparad. Provspelet före rättelserna: ~100 spel (provspel.py frö
29, `kaos.py` 3 frön × 20 scenarier, riktade lägen, krig 14 h frö 5–7), inga undantag.

**konvoj-kort, ja-boten efter rättelserna (utrett 2026-11-21):** ingen försämring av anfallet. Ja-boten
skjuter aldrig i konvoj-kort, varken före eller efter (avfyring föreslås aldrig som ja-order), så båda
utfallen är utan skott: `convoy_missed` ("kom aldrig till skott", inte en missad salva; den texten hör
till konvoj-mot) när hela konvojen hunnit 8 nm bort före tidsgränsen, annars `patrol_end`. Närmaste
avstånd till konvojen ungefär som förut (median 2,4 ⇒ 2,6 nm; efter kommer tre frön under 0,5 nm, före
inget), men färre förslag om sprint (`djup 220, turbin, fart 13` bland de vanligaste förslagen i 6 av 8
frön före, 2 av 8 efter; glesare larm under långa jakter)
gör att boten inte jagar ikapp konvojen efteråt, så den hinner förbi i 3 frön i stället för 0–1.

**Plottets kurs med osedd gir (2026-11-22, `tma.RECENT_TURN_S`):** `tma_kvalitet.py` övning, kuba, konvoj-kort,
sundet, krig-kort, 8 frön, 120 min: osäker n 913 grova 20,0 %, god n 1008 grova 5,8 % > 3σ 8,7 %, säker n 439 grova
1,1 % > 3σ 5,7 % kurs > 90° 1,1 %. `skott_saker.py` kuba, konvoj-kort, konvoj-mot, sundet-in, krig-kort, frön 1–8,
150 min, 53-61: 98 skott, 42 % träff (förut 38 %), kurs > 3σ 11 % (15 %), sundet-in 84 %, konvoj-kort 42 %,
krig-kort 15 %. Mätningen före (80 spel, säkra och goda lösningar): kurs > 3σ 39 % när målet girat de senaste 5 min,
4 % efter 20 min; varianterna "skala σ med anpassningen" och "anpassningen de senaste 3 min" flyttade under en
procentenhet.

**Provskjutning på säkra lösningar (2026-11-22, `skott_saker.py`, före rättelserna samma dag):** kuba, kuba-kort,
konvoj-kort, konvoj-mot, sundet, sundet-in, krig-kort, duell-kort, clyde-in, frön 1–30, 150 min, högst 8 skott per
spel; 493 skott med en 53-61, 223 parade med salva, 148 med SET-53. 53-61 träffar 32 %: rakt gående mål 60 %,
mål som girar under gången 4 %; gångtid < 2 min 69 %, > 6,5 min 10 %. Handelsfartyg 56 %, jagare 1 av 84 (99 % girar
under gången), transporter och tankfartyg 4–11 % (konvojens sicksack). Mot rakt gående mål: siktfel mot den ideala
kursen < 0,5° ger 71 % (gyrot och smala skott rakt för- eller akterifrån, 0–20° mellan banorna 48 %), 0,5–1° 51 %,
1–2° 23 %, > 2° nästan aldrig. Salva mot ensam torped i samma lägen 35 % mot 23 %. SET-53 sänkte ett annat fartyg i
19 av 148 skott (i sundet oftast patrullbåten: torpedrummet varnar inte för målsökande). Plottets säkra lösningar:
läge > 3σ 7 %, kurs > 3σ 18 % (mål > 3 kn; kursfel > 30° i 36 % i konvoj-mot, 24 % i krig-kort), avståndet inte
systematiskt för kort (median −0,3 %). Inget mål närmare än 0,5 nm blir säkert (golvet 0,05 nm ger 10 %). 14 % av
de säkra lägena var för djupa eller för snabba för avfyring (spärren av i omspelningen). Skott som avbröts av
tidsgränsen (mest clyde-in) räknas som missar.

**Stilla fartyg tystare (2026-11-22, `acoustics.IDLE_KN`/`IDLE_DB`):** under 3 kn faller källnivån linjärt till
12 dB under framdrivningens vid stopp (stoppad jagare 125 dB i stället för 137). `ytskott.py` 24 frön: målsökarna
påverkas knappt inom 3 nm (SET-53 23/23/23 på 1–3 nm, 125 dB hörs väl så nära), men längre ut: SET-53 på 4 nm
10 ⇒ 7 av 24, 53-62T på 5/6 nm 20/22 ⇒ 14/16. Raka torpeder som förut (inom slumpen). `kontroll.py` (alla
scenarier, 8 frön, efter torpedfelen, ellipsen och de tystare stilla fartygen): som baslinjen, inget flyttat ≥ 2;
konvoj-mot ja anfallen 5 ⇒ 4.

**Ytskott efter torpedfelen och träffellipsen (2026-11-22, `ytskott.py`, 24 frön):** träffar av 24 på
1/2/3/4/5/6 nm: 53-61 ensam 22/18/6/9/1/1, salva 21/17/15/9/5/5, SET-53 23/23/23/10 (resten utom räckhåll),
53-62T 23/23/23/23/20/22. Gyrot (σ 0,4°), blindgångare (5 %), förtidsdetonationer (2 %) och skrovets ellips
(`HULL_M`, rakt förifrån ~30 m bred, från sidan ~130 m) tar en ensam rak torped från säker till 2 nm till
ungefär 3 av 4 på 2 nm och var tredje–fjärde på 3–4 nm; salvan håller ungefär 2 av 3 på 3 nm. Målsökarna
missar bara på felen (1 av 24). Salvan är inte bättre än en ensam torped på 1–2 nm: solfjädern går minst
150 m isär vid målet, så mot ett mål från för eller akter kan bara mittorpeden träffa. Före stegen:

**Ytskott mot stillaliggande mål (2026-11-22, `ytskott.py`, 24 frön, eget spelfrö per frö och avstånd):**
träffar av 24 på 1/2/3/4/5/6 nm: 53-61 ensam 24/24/10/13/5/3, salva med tre 53-61 24/24/19/19/9/10,
SET-53 24/24/24/10 (resten utom räckhåll: 14 på 4 nm, alla på 5 och 6), 53-62T 24/24/24/24/24/23. Plottets
relativa lägesfel vid skottet median 0,010/0,013/0,038/0,039/0,055/0,073 nm mot träffradien 0,03 nm. En
ensam rak torped är säker till 2 nm och ungefär slantsingling på 3–4 nm (90 % intervall 27–58 % och
38–70 %); salvan håller 63–89 % till 4 nm. Före (2026-11-21, 8 frön) gav samma frö samma sensorslump och
bäring på alla avstånd (53-61 ensam 8/7/2/2/2/2: samma två frön träffade överallt), så det var 8 försök och
inte 48. Det som var för träffsäkert (stilla mål för högljudda för målsökarna, raka torpeder utan spridning,
träffcirkel oavsett vinkel) rättas i stegen efter.

**Provspel i 3 timmar (2026-11-21, `provspel.py`, alla långa scenarier, frö 11):** gav förslagen som
rättades den dagen (`docs/ANDRINGAR.md`). Efter rättelserna inga förslag uppåt under jakt (`upp`-kontroll i
kuba, krig, konvoj, sundet), inga undantag. `tma_kvalitet.py` övning/kuba/konvoj-kort/sundet/krig-kort, 8 frön,
120 min, kurstaket när målet kan gå: god grova 6,5 % ⇒ 5,3 %, säker grova 2,5 % ⇒ 1,7 %, säker > 3σ
9,5 % ⇒ 5,1 %. `kontroll.py` som baslinjen (31 min på 4 kärnor).

**Krigspatrullen (2026-11-20, `krig.py`, 8 frön 1–8; uppgifter a = anfall, f = foto, s = spaning):**
- `krig` passiv: tiden ute 8 (hör aldrig telegrammen på 80 m; alla uppgifter missade). Ja-boten: hemma
  (`patrol_done`) 5, tiden ute 2, förlorad 1; foto 4 av 8, spaning 0 (2 inställda), konvojen 0; inget pejlat.
  Verktyg: hemma 6, tiden ute 2, ingen förlorad; konvojen sänkt 3, foto 3, spaning rapporterad 3; 3
  fartyg sänkta, 5 sändningar pejlade. Första förslaget efter 0–6 s. Hemma efter 8–14 h (median ~12,5 h).
- `krig-kort` passiv: hemma 1, tiden ute 7. Ja-boten hemma 4 (konvojen missad 6, inställd 2). Verktyg:
  hemma 3, en konvoj sänkt. Första förslaget 0–9 min efter överlämnandet (median ~1 min).
- `kontroll.py` (frön 0–7): krig passiv tiden ute 8; ja hemma 6 (median 718 min), tiden ute 1, förlorad 1;
  krig-kort passiv hemma 1, ja hemma 5 (median 141 min). Baslinjen sparad.
- Efter provspelet (2026-11-20: konvojen i krig-kort 11–13 nm, samband var 30:e min, ingen botten och fart 4
  ut när vi är hemkallade, stabens väntan på rapport hävs av en ny uppgift): `krig` ja hemma 5, foto 3,
  spaning 2, förlorad 1; verktyg hemma 6, förlorad 2, 2 konvojer, 3 foton. `krig-kort` passiv hemma 1; ja
  hemma 4; verktyg hemma 4 och 3 konvojer sänkta (förut 1). Plottet har stora fartyg vid överlämnandet i
  8 av 8 (konvojen grupperad i 7), som konvoj-kort; förut 9–11 nm bort och i 2 frön bara handelsfartyg.
  `kontroll.py`: krig ja hemma 6 (median 674 min); krig-kort ja hemma 3 (143 min). Baslinjen sparad.
- Efter de gamla buggarna (2026-11-20: ett benförslag åt gången, `LEG_GAP_S` 300 s; ingen botten medan ett
  sambandstillfälle väntar): `kontroll.py` alla scenarier som baslinjen utom kuba-kort ja rapporterad 3 ⇒ 5
  (plottet drar inte bort båten med fyra benförslag) och krig ja hemma 6 (median 664 min; utan bottenregeln
  3: båten la sig på botten en minut efter radions "djup 40" och missade hemkallelsen). Baslinjen uppdaterad.
- Efter sammansatta förslag och `order_in_force` (2026-11-23, frön 0–7): alla scenarier som baslinjen utom duell
  ja undan 1 ⇒ 5 (sonar föreslår inte samma undanmanöver igen) och krig ja hemma 7 ⇒ 5, förlorad 1 ⇒ 2 (före
  ändringarna redan 6/1; frö 0 skiljer sig från 483 min: trimmarens "fart 6" ges nu när ett uppdrag ändrat
  farten, och resten är en annan väg i ett spel på 14 timmar). Nya: duell-torped passiv förlorad 8, ja undan 1
  (tiden ute 7); svansen-kort passiv förlorad 5, ja skakad av 4, förlorad 2. Baslinjen sparad.
- Vägen dit: utan marschfart till ankarplatsen och ut efter hemkallelsen, och med plottets TMA-ben efter
  hemkallelsen, kom ja-boten hem i 2 av 8 (foto 0); vaktjagaren som pingade i patrull hittade oss 6 nm från
  ankarplatsen (nu lyssnar den). Verktygsboten förlorades i 7 av 8 när den avböjde maskins förslag att gå
  djupt och fort bort; med förslagen 0. Jaktgruppen utan koppel jagade ja-boten i 5 h. Fingeravtrycket för
  alla andra scenarier oförändrat (60 min, 2 frön).

**Clyde (2026-11-19, N2–N6, `clyde.py`, 8 frön; passiv / ja / verktyg = djup 40 och följ Polarisbåten):**
- `clyde-in`: inspelad 0 / 4 / 4 av 8 (resten tiden ute; passiva får 1–9 min på bandet). Första förslag
  eller kontakt efter överlämnandet ≤ 3 min i 6 av 8 (Little Cumbrae skymmer ibland Polarisbåten).
  Inställt efter avståndet från farleden: 1,4–2,2 nm gav passiv 3, ja 4; 1,6–2,3 utan falska jakttecken
  ja 7; 2,0–2,8 ja 2, verktyg 1; 1,9–2,6 valt. Sonars förslag (djup 40, kurs mot kontakten) är vad ja-boten
  lever på; utan att navigatören föreslår botten och sonar skiktet under inspelningsordern föll ja till 2.
- `clyde`: passiv på grund 8 (efter 2,1–3 h: kurs 010 upp på Arrans östkust); ja ut med bandet 3,
  record_missed 5 (Polarisbåten passerade för långt bort); verktygsboten som ja. Besticksfel ≤ 0,35 nm.
- Två patrullbåtar i nästan samma bäring gav sonar falska jakttecken (deras pingar tolkades som en
  pingare med tät takt); de lyssnar nu i fred (`quiet_patrol`) och pingar först när de söker.
- `kontroll.py` (ja-boten svarar efter 20 s): clyde passiv grounded 8, ja clyde_done 3 / record_missed 5;
  clyde-in passiv 0, ja 3. Övriga scenarier som baslinjen utom jagad ja (undan 47 ⇒ 35 min, efter O1/H1/J1).
  `MAX_H` 10 h (clyde); hela kontrollen ~9 min på 4 kärnor.
- Prestanda: Firth-bottnen analytiskt 7 ms/tick, i rutnät 0,05 nm 2 ms (fel < 1 m för 99 % av punkterna).

**Kärnvapenrådet (2026-11-19, KV1–KV8, `rad.py`, 8 frön):**
- `kuba`: patrol_end 8; 23 råd, zampoliten ja 3, starpom ja 0, inga nycklar. De tre ja var signalladdningar
  som sonaren tog för skarpa med god kvalitet (plottets avstånd till jagaren var fel), alltså B-59-läget:
  zampoliten trodde på ett angrepp, starpom krävde säkerhet. `kuba-kort`: inga bomber nära, inga råd.
- `jagad`: escaped 4, nuclear 4; 22 råd, zampoliten ja 17, starpom ja 9 (bara med skadat skrov och avskuren
  stab), nycklar 9, skjutit i 4 av 8. Före B-59-regeln (starpom utan krav på skadat skrov) gav han ja i
  24 av 37 råd. `jagad-kort`: 5 råd, zampoliten ja 5, starpom ja 0 (skrovet höll).
- Rådet trodde aldrig på skarpa bomber när det bara fanns signalladdningar nära i jagad (0), och missade
  aldrig skarpa (0). Boten skjuter mot bäringen när plottet saknar lösning; först efter att boten gick upp
  till skjutdjup (≤ 100 m) sköt den alls (förut nekade torpedrummet på 170 m).
- `kontroll.py` (kuba, kuba-kort, jagad, jagad-kort, konvoj-kort, konvoj-mot) efter sonarens nya klassning
  (KV2): som baslinjen; efter KV8 alla scenarier: som baslinjen.

**Sjögången och vädret (2026-11-19, V1–V5, `kontroll.py`, 8 frön):** alla scenarier som baslinjen utom
konvojerna, som nu går i Beaufort 5 (4–6 med vädret): `konvoj` ja convoy_missed median 112 ⇒ 149 min (alla
8 missar som förut), `konvoj-mot` passiv convoy_attacked 4 ⇒ 2 och patrol_end 1 ⇒ 4, ja convoy_missed median
21 ⇒ 28 min. Kuba med vädret (3 → 4 efter 2 h), jagad, övning, sundet, arktis och duell oförändrade (B ≤ 3
ger samma brus, radar och σ som förut; övning och sundet fick background_noise +2,5 dB för att vara det vid
2). Baslinjen sparad för konvoj, konvoj-kort och konvoj-mot. `konvoj_salva.py konvoj-kort 8`: 1 sänkt
(frö 2), 1 neutralt (frö 4, som förut), mot 0–2 förut. Ja-boten i konvoj-kort (4 frön): trimmaren
föreslår fart 6 på väg upp till periskopdjup i 3 av 4; med ja bröt tornet aldrig ytan
(utan förslaget före djupet bröt det i 2 av 4).

**Duellen (2026-11-18, `duell.py`, 8 frön; utfall, i parentes andra utfall):**
- `duell`: passiv förlorad 6 (undan 2); ja-boten undan 3 (tiden ute 5, aldrig förlorad); verktygsboten
  sänkt 2, undan 2 (tiden ute 4). Första rapport ≤ 61 s.
- `duell-kort`: passiv förlorad 6 (tiden ute 2); ja-boten överlever 3 (tiden ute), förlorad 5, varken sänker
  (avfyring är kaptenens) eller kommer undan; verktygsboten sänkt 1, överlever 2. Första rapport 8–93 s.
  Medvetet svår: ubåten har redan pejlat oss. Med tre torpeder och 8 min mellan skotten.
- `svansen-kort` (2026-11-23, frön 1–8): passiv förlorad 5 (tiden ute 3); ja-boten skakad av 3, tiden ute 3, förlorad 2;
  verktygsboten som ja-boten (skjuter en gång). Första rapport 128–130 s (sonars förslag att lyssna akterut).
  Giren med fart 4 hittar ubåten inom 3 min i de flesta frön (`tests/test_tail.py`). Ubåten skjuter 0–3.
- `duell-torped` (2026-11-23, frön 1–8): passiv förlorad 8 (träffad efter 5–6 min, en efter 13); ja-boten överlever 8, undan 2
  (tiden ute 6); verktygsboten som ja-boten (skjuter aldrig: ingen lösning ≥ osäker medan den springer). Luckorna
  13–15 s efter överlämnandet; ubåten skjuter 2–3. `duell-kort` efter rättelsen av sammansatta förslag: ja oförändrad,
  verktyg tiden ute 2, förlorad 5, sänkt 1 (förut 3/4/1).

**Trim (2026-11-18, TR4):** efter trimmen (`sim/trim.py`, trimmaren) ger `kontroll.py` samma utfall som
baslinjen i alla scenarier (passiv och ja-boten, 8 frön; inget flyttat ≥ 2 av 8 eller ≥ 25 % i tid).
Arktis med ja-boten (`test_icemap`, 6 h): drivstationen 5–6 av 8 och öppet vatten 8 av 8, mot 5 och 8 utan
trim; utan regeln att barlasten bär lodräta djupändringar i låg fart och att trimmaren väntar med sina
förslag när ett annat väntar blev det 2 av 8 och två kvävda (uppstigningarna under öppningarna gick för
långsamt, och trimmarens förslag tog platsen för navigatörens).

Flyttade ur CLAUDE.md (2026-11-18). Ändra medvetet och kör sedan botarna; uppdatera här.

**Skyttebotarna och döda sektorn (2026-11-23).** `skytt.py`, alla 22 scenarier, frön 0–7 (före verktygen samma
botar i scratchpad, frön 1–8), 180 min:
- *skjut* (eld/salva på varje säker lösning, upprepar ordern): före rättelserna 33 skott, 3 träffar (alla på
  Polarisbåten i ytläge), 0 av 26 mot jagare, transporter och tankfartyg (median 4,6 nm, målet girade under gången i
  30 av 34 missar).
- *lyssna* (avstår vid frågan om långt skott, tar anfallet, skjuter på god lösning i skjutläget): 13 skott, 5 sänkta;
  med minörens 53-62T 15 skott mot ytmål, 9 sänkta.
- Plottets lösningar som inte satt sig (`Knowledge._settled`), `tma_kvalitet.py` övning, kuba, konvoj-kort, sundet,
  krig-kort, 120 min: frön 1–8 säker grova 1,1 % ⇒ 0,5 %, god 5,8 % ⇒ 2,8 %; frön 9–16 säker 2,4 % ⇒ 0,2 %, god
  6,5 % ⇒ 4,7 %; ~10 % färre säkra.
- Döda sektorn i alla scenarier, ny baslinje (`kontroll.py --spara`, commit de1a306): ja-boten clyde-in inspelad 3 av 8
  ⇒ 11 av 16, krig hemma 5 ⇒ 8 (förlorad 2 ⇒ 0), arktis stationen median 270 ⇒ 179 min, jagad förlorad median 49 ⇒
  64 min, övrigt som förut. Clyde 3 av 16 (gamla koden 4 av 16: brus). Arktis drivstationen 11 av 16 frön med och
  utan sektorn (testets gräns nu 3 av 8).
- Oraklet, ja-boten, alla scenarier: tjat 25 ⇒ 7, skjutläge för djupt 13 ⇒ 0, låg fart kvar 4 ⇒ 0, säker men fel 3
  (övningens bevakningsfartyg, `docs/TODO.md`).

**Omkört 2026-11-18** (efter slumpen per station, processbrus för sicksack q = 30 och avfyring ≤ 100 m;
`tma_kvalitet.py` och `kontroll.py` även efter golvet för avståndets σ, 0,05 nm),
8 frön om inget annat står. Siffrorna längre ned är de äldre; jämför med dessa.

**Lotsen och periskopets land (2026-11-18):** `fingeravtryck.py` (30 min, frön 0–1) ändrades bara i
`sundet-in/1` (lotsen: patrullbåten i farleden girar 20° från stranden) och `ovning-kort/0–1` (periskopet
ropar ut land). `kontroll.py` för sundet, sundet-in, sundet-ut, ovning och ovning-kort: som baslinjen
(ja-boten i ovning-kort median 48 min mot 54, inom gränsen). Lotsen: fartyg som jagar en punkt på land
håller ≥ 5 m vatten (testat 4 frön i sundet och fjorden, minst ~10 m).

| Bot | Nu | Förut |
|---|---|---|
| `konvoj_salva.py konvoj` / `konvoj-kort` | 2 / 0 sänkt | 2–3 / 1–2 |
| `konvoj_salva.py … titt` (skjuter efter titt ≤ 60 s) | 0 / 0 | – |
| `konvoj.py attack` | 1 (convoy_attacked) | 2 |
| `sundet_folj.py --följ` (grindtricket, besättningens verktyg) | 5 klara, bilder i 7 | 5, bilder i 7 |
| `sundet_in.py` passiv / ja / grind | 0 / 0 / 6 (17–32 min) | 0 / 0 / 6 |
| `sundet_ut.py` passiv / ja / ut | 0 / 0 / 5 (19–21 min) | 0 / 0 / 5 |
| `sundet.py --orakel` (smyger genom skärmen, läser sanningen) | 0 klara på 5 h, 1 genom grinden | samma skript före slumpbytet: 0, 2 genom grinden |
| `sundet.py` (samma utan sanningen) | 0 klara, 1 genom grinden | – |
| `jagad_djupt.py` | 8 (29–49 min) | 8 |
| `jagad_kort.py` passiv / ja / fast | 0 / 5 / 7 | 0 / 4 / 6 |
| `kuba_jakt.py` (12 frön) | upptäckt 11, flyget 9, 279 sjunkbomber, skrov skadat 3 | 12, 11, 338, 2 |
| `kuba_flyg.py` | 8 patrol_end, jagarkontakter 0–27, flygkontakter 0–2 | – |
| `ovning.py` | 8 training_done (103–120 min), ingen grundstötning, bestickfel 0,04–0,26 nm | – |
| `ovning_lyssna.py` | lyssning 7–25 min; plottets lösning stämmer i 5, fel i 2 | – |
| `ovning_torped.py ovning` / `ovning-kort` | träff 2 / 3 | – |
| `langvag.py kuba,jagad,konvoj,duell,sundet,arktis` (2026-11-19) | radiogram mast/långvåg/stympat: kuba 0/9/4, jagad 0/0/0, konvoj 1/0/0, duell 6/0/0, sundet 8/2/0, arktis 14/0/0; utfall som ja-boten | före långvågen (bara masten): kuba 10, jagad 1, konvoj 3, duell 6, sundet 8, arktis 14 |
| `starpom.py kuba,konvoj` (kaptenen i centralen direkt, 2026-11-19) | utfall som ja-boten; kuba 2–10 ringningar, 0–2 fara; konvoj 1–9, 1–4 | kuba 2–13, 0–2; konvoj 1–17, 1–4 (med gången 40 s) |
| `starpom.py konvoj,konvoj-kort salva` | konvoj 0 sänkt; konvoj-kort 1 anfallen, 1 neutral sänkt (frö 4) | konvoj 1 sänkt (ja-boten 2); konvoj-kort 0, 1 neutral (med gången) |
| `tma_kvalitet.py` (god/säker) | grova 3,9 %, > 3σ 6,0 % (sundet säker grova 0) | 6,9 %, 10,4 % före q för sicksack; 4,8 %, 7,9 % före golvet för σ |
| `kontroll.py` | som baslinjen efter golvet för σ (konvoj-kort ja uppdaterad efter q för sicksack) | – |
| Efter radion R3–R6 (huvudstaben, slutrapporten, radiospaning, villkorat T-5; 2026-11-19) | som raden "Efter radion R1–R2", utom arktis ja: station_reached median 295 ⇒ 336 min (5 frön; omläggningarna under öppningarna). Ryska talet rent över alla scenarier (133 typer hörda). `baslinje.json` sparad efter detta | se raderna ovan |
| Efter felrättningarna från provspelet (2026-11-18: pingare, bottenkontakt, isekolod för/akter, kortets land) | `kontroll.py` som baslinjen utom jagad ja: escaped 4 ⇒ 6, lost 4 ⇒ 2; arktis-kort ja station 5 ⇒ 4 (±1) | se raderna ovan |
| Efter radion R1–R2 (rapportens innehåll, pejlning efter längd, 2026-11-19) | som raden ovan, utom kuba-kort ja: reported 2 ⇒ 3, patrol_end 2 ⇒ 1 (kort rapport ~22 s pejlas mer sällan) | se raderna ovan |
| Efter larmförslagens 30 s (`ALARM_HOLD_S`, `MAST_ORDERS`, 2026-11-18) | `kontroll.py` som baslinjen utom kuba-kort ja: reported 3 ⇒ 2, report_missed 2 ⇒ 4, patrol_end 3 ⇒ 2 (ja-boten tar nu "djup 60" vid flygradar nära i stället för att "sänd rapport" skriver över larmet; baslinjen uppdaterad). Inom ±1: arktis ja station 6 ⇒ 5, jagad ja escaped 5 ⇒ 4, jagad-kort ja 6 ⇒ 5. 45 korta spel med ja-boten: larmförslag ersatta av rutinförslag 7 ⇒ 0 | se raderna ovan |
| Efter periskopets förstoring (Z1–Z4) | `kontroll.py` som baslinjen utom konvoj-mot (vakten tittar i hög: passiv anfallen 3 ⇒ 4, patrol_end 4 ⇒ 1; baslinjen uppdaterad); `tma_kvalitet.py` god/säker grova 3,9 %, > 3σ 6,0 % (oförändrat); `konvoj_salva.py` konvoj 2, konvoj-kort 2; `sundet_folj.py --följ` 5; `sundet_in.py` grind 6; `sundet_ut.py` ut 5; `ovning_torped.py` träff 2 | se raderna ovan |

Det neutrala fartyget i konvoj-kort frö 4: starpoms kapten sköt mot rätt mål (tankern, plottet 2,0 nm,
sanningen 4,0 nm); salvans raka torpeder gick vidare och träffade handelsfartyget S-3, som sonar hade och
klassat säkert. Ingen varnade för att det låg i skjutriktningen.

Siffrorna nedan är tagna före slumpen per station (`Game.rng_for`, 2026-11-18). Bytet ger varje frö
andra dragningar. `kontroll.py` före och efter (passiv och ja, 8 frön, 14 scenarier): kuba, kuba-kort,
jagad-kort, sundet-in, sundet-ut, konvoj, konvoj-kort, ovning och ovning-kort lika eller ±1; arktis ja
station 6 ⇒ 4 men arktis-kort ja 2 ⇒ 5, jagad ja escaped 4 ⇒ 5, konvoj-mot passiv anfallen 5 ⇒ 3 och ja
5 ⇒ 4, sundet ja 0 ⇒ 1 forced. Skillnaderna går åt båda hållen och är inom vad 8 frön ger; de särskilda
botarna är inte omkörda. `baslinje.json` är efter bytet.

- Periskopet i TMA: varje titt ger, utöver avstånd (σ 8 % + 0,03 nm), kurs (`AOB_SIGMA` efter synlig del)
  och fart (σ 2 kn) som mätningar (`BearingObs.course_obs`/`speed_obs`). En titt vars kurs avviker mer
  än max(20°, 3σ) från lösningen före titten ⇒ målet har girat, TMA börjar om från titten
  (`PlotTeam._look_turn`). Konvoj, titt var 2:a min på 2–6 nm: lösningar säker hade läge median
  0,48 nm, kurs 39°, fart 3 kn fel; nu 0,23 nm, 7°, 0,9 kn (p90 0,5 nm, 41°: girar mellan tittarna).
- Civil trafik (Kuba, `KUBA_TRAFFIC` i `scenario/kuba.py`): tre leder, 1,8 fartyg/h plus 3 från
  start, 9–14 kn, källnivå `140 + fart`. Maskering: neutralt fartyg inom 4° av målets
  bäring adderar sitt brus; ubåt < 100 m inom 0,3 nm från ett handelsfartyg får −12 dB eko
  hos jagaren. Jagaren hittar ja-boten i ~5 av 8 frön, som utan trafik.
- Ubåtsjaktflyg (Kuba, `KUBA_AIR`): första plan efter 40–80 min, 60–90 min över kvadraten,
  45–75 min mellan. Radar: master 6 nm (6 %/svep), ytläge 25 nm. MAD 250 m snedavstånd
  från 60 m höjd (säkert under ~190 m). Passiva bojar DT 8; aktiv boj 205 dB var 20:e s.
  Med flyg: jagaren hittar ja-boten i 9 av 12 frön (7 utan), flyget självt i 8 av 12. Omkört
  2026-11-15 (`kuba_jakt.py`): jagaren 12 av 12, flyget 11 av 12, 338 sjunkbomber, skrovet skadat i 2;
  2026-11-18: upptäckt 11, flyget 9, 279 sjunkbomber, skadat i 3.
- Botten (Kuba): djuphav 1 850–2 350 m, +15 m/nm norrut; bank 120–200 m med kanten 4,5–5,5 nm
  från väst- eller östsidan ⇒ ~15–18 % grundare än 300 m; berg med topp 250–400 m minst 4 nm
  från start; ränna 250–450 m djup. Kortets fel 0,5 nm (Arktis 0,8), berget saknas i 25 %.
  Arktis: slätt 3 300–3 800 m, rygg med krön 900–1 200 m ± 100–200 m.
- Jagare (alla scenarier): död zon under skrovet, ingen eko om horisontellt avstånd < djup/tan 20°
  (200 m ⇒ 0,3 nm), så en djup ubåt tappas i slutet av anfallet. Döv 60 s efter en detonation
  inom 1,5 nm. Jagare hör inte sina egna sidans pingar. Kuba efter detta: ja-boten hittas
  fortfarande 8 av 8, men jagaren tappar och återfinner kontakt 2–20 gånger (förut 1) och
  anfaller 1–19 gånger (förut 2–37).
- Sonarrummets takt: samma kontakts bäring ropas högst var 60:e s (`BEARING_MIN_GAP_S`), annars vid
  5° ändring eller var 5:e min. Pingtakt snabb vid ≤ 13 s, långsam först efter två mellanrum ≥ 20 s
  i rad (en missad ping vänder den inte). Jagade, ja-boten: ~5 rapporter/min under jakten (förut ~11).
- Pingarnas styrka (2026-11-21): en jagarping (230 dB) hörs på 50–100 nm i lugn fart, ekot når bara
  ~4,4 nm. Snabb takt räknas som jakt på oss bara med mottagen nivå ≥ 142 dB (`PING_NEAR_RL`, ~8 nm;
  under skiktet lägger operatören till 7 dB). Svagare: `sonar.ping.fast_far` utan larm, högst var 15:e
  min per pingare. Krig ja, 24 frön: förlorad 2 ⇒ 4 på olika frön (brus), stridslarm 67 ⇒ 60; övriga
  scenarier som baslinjen.
- Sonar publicerar `HuntSigns` vid snabb pingtakt med starka pingar och plask; `Knowledge.hunted()` (5 min). Då
  föreslår maskin `eng.suggest.sprint` (turbin, djup ≤ 220 m, fart = kavitationsfart − 1)
  i stället för smygmotor, och sonar föreslår inte fart 4 när en kontakt tappas.
- Jagade (`jagad`, `hunted_scenario`): ubåten börjar 45 m, 6 kn, 1,3 nm från bankens
  300-meterskurva på djupt vatten; DD1 2,2–3 nm i norr med färsk kontakt (`start_hunt`), DD2
  7–8,5 nm i söder. Jagarna är `partners` och delar fix (σ + 0,4 nm). `escalate_after=3`:
  skarpa efter tre övningsanfall (~25 min). `leash_nm=1`: släpper jakten när datumet ligger mer
  än 1 nm utanför kvadraten. Mål `EscapeGoal`: 1 nm utanför och ingen jägare med datum
  inom max(1 nm, 3σ) från oss (ett skenmål räknas inte). Navigatören (`exit_route`) föreslår
  närmaste kant, +4 nm straff inom 40° från en hotkontakt, och sträckan där kortet visar grundare än
  300 m (`EXIT_DEEP_M`) räknas dubbelt: över banken kan vi inte springa djupt. 8 frön: passiv 0,
  ja-boten 6 (15 av 24), djupt och fort (turbin 12 kn, 200 m, navigatörens väg ut vid start, ja till
  djupförslag) 8. Utan grundstraffet gick vägen ut ofta över banken och ja-boten klarade 2 av 24
  (vilket förslag som kommer först beror på rapporternas slumpade fördröjning).
- Jagade kort (`jagad-kort`, `hunted_scenario(short=True)`): kvadraten 7 nm, ubåten 2–2,5 nm från
  djupvattensidans kant, DD1 1,4–1,7 nm bort i anfall, DD2 3–3,8 nm bort på djupvattensidan, båda
  skarpa från start; tidsgräns 30 min. 8 frön: passiv 0, ja-boten 4 (24–26 min), djupt och fort
  (navigatörens `exit_route` var 60:e s) 6 (19–27 min); omkört 2026-11-18: 0, 5, 7. Sonar hör jakten efter 6–8 s.
  Medan vi är jagade (`Knowledge.hunted`) föreslår plottet inga TMA-girar, och maskinens sprintförslag
  har alltid med `turbin` (förslaget levereras sent).
- Kust (`seabed.Coast`, `strait_seabed`): land har negativt djup (`Seabed.min_depth` < 0),
  sjökortet ritar land (`░`) och kustlinje. Tidvatten (`environment.TidalStream`, period 12 h 25 min)
  skalar med djupet: `peak·clamp(60/djup, 0,2, 1,5)`; `Environment.current_at(x, y, t)` används för
  alla fartyg och torpeder. Navigatören räknar besticket med `Knowledge.tide_table` (fel ±20 % och
  ±20 min) och lägger 0,3·|tidvatten| per timme på σ. Landvarning (`_land_watch`) föreslår gir när
  kortet visar < 21 m framåt. Fix nära land (land inom 8 nm dag, 5 natt): 30 s / 45 s, σ 0,05.
  Vägen ut (`exit_route`) går aldrig över land; finns ingen rak väg söker den på kortets rutnät.
  Efterklang på grunt vatten (`seabed.shallow_reverb`): aktiv sonar −15 dB vid 0 m, 0 vid 100 m.
  Navigatören tittar 6 min framåt, minst 0,6 nm (förut 1 nm).
- Hamnskydd (`harbor.py`): hydrofoner DT 10, rundstrålande: kustbrus 64 dB plus alla fartyg inom
  5 nm (smygmotor 3 kn hörs < 0,15 nm, turbin 5 kn ~0,5 nm; ett fartyg nära dränker oss). Nät med
  grind ±0,1 nm som är öppen 4 min efter att ett fartyg varit inom 1 nm; hamnlederna har brytpunkter
  (`Lane.via`) så att fartygen går genom grindens mitt. Patrullbåt (`PatrolBoatAI`): ping 196 dB
  (~0,5 nm under skiktet, ~1 nm över), 6 kn, ping var 45:e s i patrull, master inom 2 nm med 1 %/s,
  skärm 1,5–2,5 nm ut. Ett fartyg på väg in inom 6 nm från grinden eskorteras (`escort`, 0,4 nm
  framför) till grinden. Jägare tar aldrig emot ett datum utanför `leash_nm` (gäller även Jagade).
  Förtöjda fartyg (`moored`) driver inte.
- Navigatören `följ S-3`: styr på kontaktens bäring var 15:e s och håller plottets fart (tills
  kaptenen sätter farten själv); `kurs` avbryter.
- Sundet (`sundet`, `strait_scenario`), 7 h, ett fartyg in efter 45–75 min, sedan 0,6/h in och ut
  i lotsfart (6–8 kn). Grindtricket: vänta söder om grinden, `turbin, djup 40, följ S-x` när
  fartyget passerat 0,2–0,45 nm, foto innanför, följ ett utgående fartyg ut. 8 frön: bot med bara
  besättningens verktyg (`sundet_folj.py --följ`) klarar 3 (goda bilder i 6; omkört 2026-11-15 och
  2026-11-18: 5, bilder i 7), samma bot som läser sanningen (`sundet_folj.py` utan `--följ`) 5 (bilder i 8;
  inte omkört). `sundet.py --orakel`, som smyger genom skärmen utan fartyg, klarar 0 på 5 h (genom
  grinden i 1–2, före och efter slumpbytet);
  ja-boten och den som försöker smyga genom skärmen utan fartyg klarar 0. Botarna i scratchpad
  (`follow_bot.py`, `strait_bot.py`).
  Väntläget (första steget, `_harbor_watch`/`_wait_point`): före fotot och utanför nätet föreslår
  navigatören `smygmotor, väntläget`: 1,4 nm ut från nätet åt det håll kortet visar djupast vatten
  (farleden), 0,35 nm vid sidan åt vår sida, ≥ 40 m på kortet; ritas som känd plats `Väntläget`.
  `väntläget` styr dit (5 kn, 3 kn inom 5 nm från nätet) och håller läget i 1–2 kn; `kurs` eller `fart`
  avbryter. Resten (följ, foto, ut) föreslås inte. 8 frön, bara detta förslag: framme i 8 efter
  ~100 min, första fartyget in passerar 0,1–0,6 nm (oftast 0,3–0,55); patrullbåten får kontakt
  under passagen genom skärmen i 7 (passiv bot 3), oberoende av djup.
- Sundet in (`sundet-in`, `strait_scenario(short=True)`): 06:20, vakt 10 min (`smygmotor, väntläget`),
  ubåten startar ~1,4 nm utanför nätet 0,35 nm vid sidan, ett fartyg på väg in 3,0–3,2 nm från nätet vid start
  (passerar väntläget 3–5 min efter överlämnandet), inga fler in. Mål `PhotoGoal`: foto minst god ⇒
  `photo_taken` (ingen utväg). Tidsgräns 35 min efter överlämnandet. 8 frön: passiv 0, ja-boten 0 (följandet
  föreslås inte, kaptenens sak), grindboten (`turbin, djup 40, följ S-x` när fartyget passerat 0,2–0,45 nm,
  `kurs mot ankarplatsen, fart 4, periskopdjup` 0,6 nm innanför, `foto`) 6, på 18–33 min.
- Sundet ut (`sundet-ut`, `strait_scenario(out=True)`): 07:00, startläget byggt direkt: innanför nätet 1,0–1,2 nm,
  0,2 nm vid sidan av farleden på periskopdjup; vakten (4 min) tar `foto` (bilden via bussen) och går till 20 m
  på smygmotor. Ett fartyg ut startar 0,9–1,2 nm bakom oss (passerar 3–6 min efter överlämnandet), inga fler.
  Ute = söder om `Scenario.escape_y_below` (1 nm söder om nätet) och ingen har oss; navigatörens väg ut räknar
  mot linjen. Tidsgräns 30 min. 8 frön: passiv 0, ja-boten 0, utboten (periskoptitt var 60:e s, `turbin, djup 25,
  följ S-x` när fartyget passerat 0,2–0,45 nm, efter 1,2 nm söderut fart 10) 5, på 16–22 min
  (omkört 2026-11-15: 5, på 20–26 min).
- Konvojen (`konvoj`, `convoy_scenario`): 28 okt, krig, 06:30 (dagsljus). Konvoj (2 trupptransporter,
  1 tanker) och 2 eskorter, baskurs 190–230°, start 16–20 nm bort, vägen passerar oss på 1,5–5 nm;
  ordern ger läge (±2 nm) och kurs avrundad. Mål `StrikeGoal`: minst ett mål sänkt och ingen
  jägare har oss 10 min efter senaste sänkningen ⇒ `convoy_attacked`; alla mål > 8 nm och förbi oss
  ⇒ `convoy_missed`. Kuba-trafik och flyg finns kvar. Träffytan är skrovets ellips (`weapons.HULL_M`,
  halva längden och bredden per typ, plus `FUZE_M` 10 m; sedan 2026-11-22, förut en cirkel med halva längden). Salva (`salva S-x`, `eld tub 1-3 mot S-x`):
  raka torpeder i solfjäder, avstånd vid målet = lägesfelet (σ avstånd, fart, kurs under gångtiden)
  inom 0,08–0,25 nm; hel eller inte alls (alla tuber prövas före första avfyringen, `_refusal`),
  omvänt intervall (`3-1`) = samma tuber. Sonar håller isär okända pingare på en utjämnad bäring (grind 8° + 0,15°/s sedan förra pingen, högst 20°). 8 frön: passiv 0, ja-boten 0,
  bot med besättningens verktyg (periskop var 4:e min, `anfall`, salva mot klassad transport/tanker
  inom 3 nm, sedan djupt bort) 3 (och 1 neutral sänkt). Boten i scratchpad (`convoy_bots.py`).
- Konvojen kort (`konvoj-kort`): konvojen 13–15 nm bort, vakt 35 min (periskopdjup, fart 3, svep var
  4:e min), sedan 45 min. 8 frön: plottet har konvojen vid överlämnandet i alla, 5–9 nm bort, ingen
  eskort har oss; första förslag 0–3 min efter; ja-boten i skjutläge i 4 (9–34 min). Bot som skjuter
  `salva` (upprepad) mot klassad transport/tanker ≤ 3 nm med lösning ≥ osäker: sänker 1 på 28 min
  (samma bot i `konvoj`: 1, på 69 min). Uppvärmningen tar ~5–8 s. Efter plottets periskoprättelse:
  `konvoj` 2 av 8, `konvoj-kort` fortfarande 1 av 8 (omkört 2026-11-15 med `konvoj_salva.py`: `konvoj` 3
  av 8 på 57–60 min, `konvoj-kort` 2 av 8; `konvoj.py attack` 2 av 8); boten skjuter på gamla lösningar (titt var 4:e min,
  ben på 5–10 min). Titt före skottet (vakthavande, ≤ 3,5 nm, var 90:e s) byggd 2026-11-18. 8 frön 2026-11-18,
  efter processbruset för sicksack: `konvoj_salva.py` konvoj 2, konvoj-kort 0; med `titt` (skjuter bara efter
  en titt ≤ 60 s) 0 och 0 (eskortens radar håller oss oftast under periskopdjup); `konvoj.py attack` 1.
  Salvaboten skjuter mest på osäkra lösningar, med 1–4 nm avståndsfel.
- Konvojen motanfall (`konvoj-mot`, `convoy_counter_scenario`): ledpunkten 1–2 nm före tvärs, vi 1,8–2,4 nm
  vid sidan. Vakten (`_CounterattackWatch`): periskopdjup, titt var 60:e s, `salva` (två gånger) mot
  stort fartyg med lösning ≥ god, ≥ 60 s sedan senaste gir, titt ≤ 60 s gammal, fart ≤ 20 kn, ≤ 2,5 nm;
  överlämnar när torpedrummets gångtid − 45 s gått (2–4 min in) och sätter `patrol_end` +30 min. Har ingen
  eskort oss då ger närmaste eskort färsk kontakt (σ 0,1 nm, torpedbanorna). Eskortens koppel 6 nm.
  Eskorternas ping hittar oss på 1,3–1,9 nm även under skiktet, så att gömma vakten går inte.
  8 frön: vakten skjuter i 8, träff i 6 (25–155 s efter överlämnandet); passiv 3, ja-boten 4,
  djupt och bort (turbin 12 kn, 200 m, bort från hotet) 6 (omkört 2026-11-15: passiv 5, ja 5, bort 6).
- Eskorter (alla konvojer): en eskort med egen kontakt ≤ 40 s gammal och < 0,8 × den jagandes avstånd till
  datumet tar över jakten (`_closer_than`); i anfall går eskorten `SPEED_CLOSE` tills den är 1 nm från
  datumet (förut anfallsfart 15 kn hela vägen, så den hann sällan fram innan kopplet släppte).
- Kvadrat 7 kort (`kuba-kort`, `kuba_short_scenario`): jagaren 3–4 nm bort i patrull (övningsbomber), vakt
  15 min (smygmotor 3 kn på 100 m, gir +70° efter 7 min), sambandstillfälle 5 min efter överlämnandet i 15 min,
  sedan 10 min. Flyget efter 5–10 min. Mål `ReportGoal`: rapport sänd inom fönstret (`last_report_t`)
  och, när fönstret stängt, ingen jägare med datum σ ≤ 0,5 nm på oss (`_hunting_us(max_sigma=...)`; pejlingen
  av sändningen, σ 1,5, räknas inte) ⇒ `reported`; ingen rapport ⇒ `report_missed`. Radion (`report_required`):
  väntar (`radio.wait`) så länge plottet har en hotkontakt ≥ osäker närmare än 5 nm (`RADIO_SAFE_NM`), föreslår
  antenndjup när den gått längre bort (`radio.clear`), sedan periskopdjup och `sänd rapport` (inte när vi är
  jagade). Förvarningar under vakten ges igen vid överlämnandet. Sonar föreslår inte skiktet medan radion
  behöver masten (`RadioStation.needs_mast`), utom när vi är jagade. 8 frön: plottet har jagaren vid
  överlämnandet i 7, passiv 0, ja-boten 4 (rapporten sänd i 7).
- Packis (`ice.py`): rutor 0,05 nm, flerårsis 2–4,5 m, kölar 8–25 m (6 % 30–45 m),
  170 råkar, 28 polynyor ⇒ ~4–5 % öppet vatten, en öppning ungefär var 30:e minut
  i 5 kn. Tornets topp 13 m och skrovets 8 m över kölen. Tunn is ≤ 1 m bryts i
  ≤ 2 kn på 40 s. Isdrift 0,25 kn mot 200°. Isbrus 50 dB (fast is) till 72 dB.
- Arktis: generatorn 142 dB, US-ubåt 125 + 1,5·fart med DT 0 och egenbrus 48 + fart.
  Mål: ytläge inom 1,5 nm från Nord-7. Ja-boten når målet i 9 av 12 frön (omkört 2026-11-15 efter
  plottets ärliga kvalitet; förut 7, ännu tidigare angivet ~10).
- Arktis kort (`arktis-kort`, `arctic_scenario(short=True)`): stationen 3,6–4,2 nm norrut vid start, vakt
  20 min (`kurs mot Nord-7, djup 60`), alltså 1,7–2,6 nm kvar vid överlämnandet; nödsignalens läge känt
  (σ 0,6). US-ubåten 5,5 nm från stationen vid start (2,5–5 nm från oss vid överlämnandet, oftast ohörd).
  Branden 5–12 min efter överlämnandet, tidsgräns 35 min. Navigatörens sökspiral runt stationen och
  maskinens förslag att ventilera vid en öppning tar inte över när vi är på väg upp (beordrat djup ≤
  periskopdjup). Uppstigning stilla ~0,25 m/s, därför 60 m. 8 frön: passiv 0, ja-boten 2.
- Brand (arktis, 40–110 min): rök 0,0009/s medan det brinner (7–13 min), sedan
  +0,2/h tills ventilation (−0,02/min på periskopdjup, −0,05/min i ytläge). Rök 1,0 = förlorad.
  Röken sänker `effective_skill()` med upp till 50 %.

