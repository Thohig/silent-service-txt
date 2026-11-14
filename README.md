# K-114 – textbaserad ubåtssimulator, 1962

Du är kapten på en sovjetisk atomubåt. Du ger skrivna order och besättningen
rapporterar. Fienden syns aldrig direkt, bara genom sonaroperatörens bäringar
och plottlagets målrörelseanalys.

## Köra

```bash
uv run main.py                     # scenarioväljare, slumpat frö
uv run main.py --scenario kuba     # hoppa över väljaren (kuba, jagad, sundet, arktis)
uv run main.py --seed 4            # reproducerbart scenario
uv run main.py --tyst              # utan ljud
uv run pytest             # tester
```

Avsluta med `ctrl+q`. Sanningen (exakta positioner och TMA-lösningar) loggas
till `logs/truth-*.log`.

## Order

Besättningen föreslår själv åtgärder. Ett förslag med en färdig order visas
som `[ja: …]` och på statusraden. Svara `ja` för att verkställa eller `nej`
för att avslå. Du kan också be om förslag: `förslag` upprepar det som
väntar eller ger besättningens viktigaste förslag just nu, `förslag sonar`
frågar en viss station och `annat förslag` ger nästa i tur.
Avfyring föreslås aldrig som en ja-order.

Besättningen talar som i den sovjetiska flottan, med några fasta ryska fraser:
*Jest* (ska ske), *Tovarisjtj komandir* (kamrat befälhavare), *Boevaja trevoga*
(stridslarm), *Avarijnaja trevoga* (haverilarm) och *Torpeda vysjla* (torpeden har
lämnat tuben). Betydelsen framgår alltid av den svenska texten bredvid, och `hjälp`
har en ordlista. Siffror och bedömningar är alltid på svenska. `jest` fungerar som `ja`.
Efter ett haverilarm rapporterar avdelningarna inom en minut vad de har inspekterat.

Med ljudet på talar besättningen ryska (macOS-rösten Milena), medan loggen alltid är
på svenska. `tal svenska` byter till svenskt tal, `tal ryska` tillbaka. Saknas Milena
talar besättningen svenska.
Ger du själv en order om samma sak (till exempel `fart 6` när besättningen
föreslagit `fart 4`) släpps förslaget, och besättningen föreslår aldrig en
kurs, fart, framdrivning eller ett djup som redan är beordrat.

Är kaptenen tyst i tio minuter (simtid) och ingen annan har föreslagit något,
tar vakthavande initiativ och låter den station som har det viktigaste
förslaget säga det: omstart av reaktorn, gå under skiktet, smygmotor, nytt
ben för plottet, påminnelse om sambandstillfälle, lägre fart för att lyssna,
fix, ladda tom tub, periskopsvep eller nytt sökben. Samma order föreslås
inte igen inom tjugo minuter. Svarar kaptenen inte på ett förslag glesas upprepningarna
ut: väntetiden fördubblas för varje obesvarad gång (larm undantagna).

| Område | Order |
|---|---|
| Manöver | `kurs 090` · `fart 5` · `stopp` · `djup 100` · `periskopdjup` · `antenndjup` · `ytläge` |
| Förslag | `ja` · `nej` · `förslag` · `förslag sonar` (maskin, plott, navigatör, torped, radio, vakthavande) · `annat förslag` |
| Tid | `tid 1` `tid 2` `tid 5` `tid 10` (faller till 1× vid larm) |
| Sonar | `aktiv sonar` (ger avstånd men avslöjar oss) |
| Plott | `läge S-1` · `plot S-1` |
| Navigation | `position` · `fix` (periskopdjup) · `kurs mot <plats>` · `följ S-1` (i kontaktens kölvatten) · `ekolod` · `isekolod` · `vak` (gå till och stoppa under en loggad öppning i isen) · `drivstationen` (styr mot Nord-7) · `botten` (lägg oss stilla på botten; `djup` eller `fart` lättar) · `bottenfix` (nio lodningar på tre minuter jämförs med sjökortets djup) |
| Maskin | `smygmotor` · `turbin` · `stäng reaktorn` · `starta reaktorn` · `nödblåsning` · `maskin` · `ventilera` (periskopdjup i öppen luft) |
| Vakthavande | `periskop` · `radar` (periskopdjup; radarvarnaren är automatisk) · `foto` (periskopfoto av ankarplatsen) |
| Radio | `sänd rapport` (periskopdjup, kan pejlas) · `radio` |
| Torped | `tuber` · `torpeder` · `skjutlösning S-1` · `eld tub 1 mot S-1` · `eld tub 1 kurs 045` · `ladda tub 7 SET-53` · `skenmål` |
| Ljud | `ctrl+t` eller `ljud` / `ljud av` / `ljud på`: besättningen talar (macOS-rösten Alva, de ryska fraserna med Milena om den finns), larmen går det sonaren hör spelas i stereo (babord till vänster) och båten låter: reaktor, turbin, skrov, is, brand och kontakternas propellrar |
| Vyer | `Tab` växlar logg → sjökort → djupprofil → systemtavla → logg; `Esc` går tillbaka till loggen. Orden `sjökort`, `profil` och `system` öppnar en vy direkt |
| Sjökort | Navigatörens sjökort i helskärm; `+`/`-` zoomar, pilarna flyttar, `c` centrerar |
| Systemtavla | Ubåtens system på en tavla: genomskärning av de nio avdelningarna (brand, rök, skador, reaktorns läge, vatten i kölsvinet), maskin (reaktor, framdrivning, batteri, tryckluft, skrov, vatten, koldioxid, rök), skador och reparationer per komponent, navigation, torpedtuberna med laddning, sonar och samband. Allt ur besättningens egna instrument; ▲ varning, ■ fara |
| Djupprofil | Visar ubåten från sidan över tid: vårt djup, beordrat djup, ytan, periskopdjup, språngskiktet, prov- och krossdjup, isen ovanför, botten där ekolodet lodat och det sonar hört; `+`/`-` djupskala, pilarna tidsskala, `a` automatisk skala. Djupmätaren till höger om loggen visar samma sak i kort form |
| Övrigt | `hjälp` · `avsluta` (avbryter patrullen med slutrapport) · `ctrl+q` stänger programmet |

Flera order kan ges på en rad, åtskilda med komma, semikolon eller "och":
`kurs 090, fart 5; djup 100`. De verkställs i tur och ordning. Ett komma
följt av en siffra är decimalkomma (`fart 5,5`). Förstår besättningen inte
en del säger de vilken, och resten verkställs ändå.

## System ombord

| System | Spelmässig betydelse |
|---|---|
| Reaktor, turbin, smygmotor, batteri | Fart mot ljud. Kylpumparna brusar alltid; att stänga reaktorn ger tystnad men tömmer batteriet. Snabbstopp kan inträffa. |
| Kavitation | Över en viss fart (högre på djupet) hörs ubåten långt. |
| Språngskikt (60 m, Kuba) | Skyddar mot jagarens sonar, men vi hör också sämre genom det. |
| Roder, barlast, skrov | Djupändring kräver fart. Under provdjup (300 m) knakar skrovet; 450 m krossar det. |
| Skador, läckor, nödblåsning | Sjunkbomber ger skador och vatteninträngning; reparationer tar tid. |
| Passiv och aktiv sonar | Passiv ger bäringar; aktiv ger avstånd men avslöjar oss. |
| Periskop, radar, radarvarnare | Avstånd och kurs på periskopdjup, med risk att synas. |
| Navigering | Besticket driver med ström och loggfel; fix kräver periskopet. |
| Havsbotten | Botten varierar: vid Kuba en bank på 120–200 m längs ena sidan, ett undervattensberg och en ränna i djuphavet; i Arktis en rygg vars krön når cirka 1 000 m. Sjökortet har djupkurvor från ett gammalt kort, förskjutna och utjämnade, och ibland saknas berget. Ekolodet (`ekolod`) ger det verkliga djupet men hörs. Går vi in i botten i mer än 2 knop går vi på grund: skador på skrov, sonar eller roder och läckor i högre fart. Navigatören varnar när kortet eller en färsk lodning visar grundare vatten framåt, och osäkrare ju äldre besticket är. Grundare än provdjup kan vi lägga oss stilla på botten (`botten`): maskinen stoppas, kylpumparna går på lågvarv och jagarens eko drunknar i bottenekot. Sand och lera är mjuka; klippbotten (berg, ryggar, branta sluttningar) skrapar skrovet. Bottentypen står på sjökortet, som kan ha fel. Navigatören föreslår det när vi är jagade över grunt, mjukt vatten. Fix mot botten (`bottenfix`) går utan periskop, även under isen: nio lodningar i minst två knop matchas mot kortet. Längs en rak sluttning ger det bara en lägeslinje, vid ett berg eller en ränna läget i båda led, och aldrig bättre än kortet (0,5 nm vid Kuba, 0,8 i Arktis). Saknar kortet något säger navigatören det och låter besticket vara. Lodningarna hörs. |
| Radio | Sambandstillfällen på antenndjup (tider beror på scenariot). Sändning pejlas. |
| Jagade (`jagad`) | Spelet börjar mitt i jakten, kl 00:40: en jagare har just fått kontakt på 2–3 sjömil och en till kommer söderifrån. Jagarna delar sina fix över radio. Efter tre anfall med signalsjunkbomber går de över till skarpa. Smyga hjälper inte när de redan har oss: djupt och fort, och sväng när de går in för anfall, för skrovsonaren ser inte rakt ned och efter detonationerna är den döv en minut. Målet är att lämna kvadrat 7 (en sjömil utanför kanten, längre följer jagarna inte efter) utan att någon jagare eller något plan har kontakt. Navigatören föreslår kortaste vägen ut som inte leder mot en hotkontakt, och banken på ena sidan ger möjlighet att lägga sig på botten. Flyget kommer efter 25–45 minuter. |
| Sundet (`sundet`) | Guantánamo, 04:20, gryning 06:10. In mot inloppet från havet: en patrullbåt håller en skärm på djupt vatten 1,5–2,5 sjömil ut, hydrofoner ligger på botten en halv sjömil ut och ett nät spärrar farleden. Grinden i nätet öppnas när ett fartyg ska igenom; periskopet ser bojarna och om grinden är öppen. Patrullbåten eskorterar fartyg på väg in fram till grinden. Den som följer tätt efter ett fartyg (`följ S-3`: navigatören styr på kontaktens bäring och håller plottets fart) göms i dess brus och kölvatten och kommer in genom grinden; ut kommer man på samma sätt. Fotografera ankarplatsen (`foto`, dagsljus, ju närmare desto bättre bild; god bild krävs) och ta er ut. `kurs mot ankarplatsen` / `kurs mot nätet` styr mot kända platser. Tidvattnet sätter in och ut i farleden; navigatören räknar med tabellen, som har fel. Nära land tar navigatören fix på landmärken på en halv minut. På grunt vatten dränks aktiv sonar av efterklang. |
| Arktis: Nord-7 | Drivstationen driver med isen. Huvudstaben ger en ungefärlig position; generatorn hörs på några sjömil och ljuset syns i periskopet. Målet är ytläge inom 1,5 sjömil. En amerikansk atomubåt hör oss före vi hör den och skuggar oss, men skjuter inte. |
| Brand och rök (arktis) | En brand i turbinrummet stoppar turbinen. Röken stiger tills vi ventilerar i öppen luft och sänker besättningens förmåga; för tät rök kväver besättningen. |
| Isljud (arktis) | Bakgrundsbruset beror på isen. Skruvis knakar och kan först tas för en kontakt. |
| Packis (arktis) | Masterna kräver öppet vatten. Isekolodet lodar isen ovanför och navigatören loggar öppningar; deras läge blir osäkrare när isen driver. Kölar når 45 m: gå djupt i fart. Tunn is (≤ 1 m) kan brytas igenom i låg fart om råken är minst 120 m. Arktiskt hav saknar språngskikt; djupt gående hör och hörs längre. |
| Civil trafik (Kuba) | Handelsfartyg går genom kvadraten i tre leder; sovjetiska fraktfartyg mot Kuba stoppar när jagaren kommer nära och vänder hem. De hörs som okända kontakter tills sonar klassat dem. Deras brus kan dölja oss: under ett handelsfartyg (inom ett par kabellängder, grundare än 100 m) drunknar vårt eko i dess kölvatten. Att sänka ett civilt fartyg avslutar patrullen, och torpedrummet frågar en gång innan det skjuter mot något som inte är säkert klassat som örlogsfartyg. |
| Ubåtsjaktflyg (Kuba) | Ett patrullflygplan kommer efter 40–80 minuter och stannar en dryg timme, sedan nästa. Det hörs inte under vattnet. Radarvarnaren hör flygradarn och periskopet ser planet i dagsljus. Flyget ser master och ubåt i ytläge på radarn, fäller sonobojar (sonar hör plasken, och en aktiv boj pingar från en fast punkt) och flyger lågt med magnetisk spaning: djupare än cirka 190 meter går det rakt över oss utan utslag. Det flyget hittar får jagaren, och flyget går dit jagaren tror att vi är. |
| Torpeder | 53-61 (rak, snabb), SET-53 (målsökande), T-5 (kärnladdning, spärrad utan order). |
| Torpeder i vattnet | Sonar följer egna torpeder. Torpedrummet rapporterar normal gång, sväng (målsökning), tappad torped, detonation och miss. `torpeder` ger gångtid, tid till beräknad träff, räckvidd kvar och senaste bäring. |
| Skenmål | Drar jagarens sonar bort från ubåten. |

Jagaren pingar, söker kring sin bild av var vi är och fäller
signalsjunkbomber för att tvinga upp oss. Om vi skjuter blir sjunkbomberna
skarpa.

Sjökortet visar bara det besättningen vet: navigatörens beräknade
position med osäkerhetsring, besticket och fixarna, plottlagets lösningar
(läge, fartvektor, avståndsosäkerhet) och bäringar utan lösning, isekolodets
lodningar och öppningar, huvudstabens positioner och egna torpeder. Allt ritas
där besättningen tror att det är, så kortet blir lika fel som besticket tills
nästa fix. Spelet går vidare medan kortet visas, och de senaste rapporterna
syns längst ner.

Spelet slutar om ubåten förloras, tvingas till ytan, sänker jagaren,
när patrullen är slut kl 08:00 eller när kaptenen skriver `avsluta`. Då visas
en kort rapport: tid i befäl, order, kontakter, torpeder, sjunkbomber,
skador, radio och de viktigaste händelserna. Rapporten bygger på
loggboken (`sim/logbook.py`), alltså på vad besättningen rapporterat.

## Arkitektur

```
sim/                 ren Python, ingen Textual
  world.py           SANNING: exakta positioner
  sonar.py           sensorn: enda bryggan sanning -> brusiga observationer
  knowledge.py       KUNSKAP: byggs bara från händelser på bussen
  tma.py             bäringsbaserad målrörelseanalys
  events.py          händelsebussen
  orders.py          orderregister (CommandSpec/CommandRegistry)
  reports.py         strukturerade rapporter + rapportfilter
  phrases.py         frasbok: rapportdata -> svensk text
  game.py            tunn samordnare: tick, order, leverans
  environment.py     ljudprofil (språngskikt/arktis), ström, dygnsljus
  ice.py             SANNING: packis, kölar, råkar, drift, kontakt med isen
  icemap.py          KUNSKAP: iskartan ur isekolodets lodningar
  scenario.py        scenarier och scenarioregistret
  arctic.py          SANNING: drivstationen och den amerikanska ubåtens AI
  traffic.py         SANNING: civil trafik, leder och handelsfartygens AI
  air.py             SANNING: ubåtsjaktflyg, sonobojar och MAD
  entities.py        fartyg, transienter, emissioner
  ownship.py         egen ubåt: reaktor, batteri, skrov, skador
  enemy.py           jagarens sensorer och beteende
  weapons.py         torpeder, sjunkbomber, skenmål
  firecontrol.py     skjutlösning (ren matematik på kunskap)
  chart.py           sjökortets ritelement; stationerna bidrar via chart_items()
  seabed.py          SANNING: bottentopografi; chart_copy() ger sjökortets bild (kunskap)
  profile.py         djupprofilens element; stationerna bidrar via profile_items()
  systems.py         systemtavlans element; stationerna bidrar via system_items()
  stations/          ett system ombord per modul
    base.py          Station: COMMANDS, on_order, update, say, suggest
    navigation.py    kurs, fart, djup, bestick, fix, ekolod, isekolod, vak
    engineering.py   maskin och skadekontroll
    sonar_room.py    sonar, transienter, aktiv sonar
    officer.py       periskop, radar, radarvarnare
    radio.py         sambandstillfällen och rapporter
    plot.py          plottlaget
    torpedo_room.py  torpedrum och eldledning
ui/                  Textual
  audio.py           tal, larm och hydrofonljud (say/afplay)
  ambience.py        bakgrundsljud: mixer och slingor (sounddevice)
  chart.py           sjökortet i helskärm
  chart_render.py    rastrering av sjökortet till tecken
  profile.py         djupprofilen i helskärm
  profile_render.py  rastrering av djupprofilen och djupmätaren
  systems.py         systemtavlan i helskärm
  systems_render.py  genomskärning och paneler till tecken
```

### Lägga till ett system

1. Skapa `sim/stations/<system>.py` med en klass som ärver `Station`.
2. Definiera ordertyper (`Order`-dataklasser) och `COMMANDS` med
   `CommandSpec(mönster, bygg, hjälptext)`.
3. Hantera dina order i `on_order` och kör löpande logik i `update`.
4. Rapportera med `self.say("system.händelse", {...data...})` och registrera
   fraser med `phrases.register({...})` i stationens modul. Föreslå åtgärder
   med `self.suggest(nyckel, typ, data, order="…")`.
5. Vill stationen ta initiativ när kaptenen är tyst: returnera `Proposal`
   från `idle_proposals()` (prioritet 1 = viktigast). Vakthavande väljer.
5. Ska systemet synas på sjökortet: returnera element (`sim/chart.py`) från
   `chart_items()`, i beräknade koordinater och bara ur kunskap.
5. Ska systemet synas i djupprofilen: returnera element (`sim/profile.py`)
   från `profile_items()`, bara ur kunskap.
5. Har systemet egna instrument ombord: returnera element (`sim/systems.py`) från
   `system_items()`; en ny panel dyker upp på systemtavlan av sig själv.
5. Lägg klassen i `DEFAULT_STATIONS`. Game behöver inte ändras.

Stationer pratar med varandra via händelsebussen. Kunskapslagret
registreras före stationerna, så en station ser alltid uppdaterad kunskap.

### Utbyggnadspunkter

- **Trötthet, lojalitet, sabotage:** rapportfilter i `ReportQueue.filters`
  ändrar `report.data` före formulering. Skicklighet går via
  `CrewMember.effective_skill()`.
- **Tal (macOS `say`):** prenumerera på `ReportDelivered`.
- **Berättelselager, politisk officer:** prenumerera på händelser och
  skicka egna rapporter.
