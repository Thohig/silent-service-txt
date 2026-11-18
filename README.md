# K-114 – textbaserad ubåtssimulator, 1962

Du är kapten på en sovjetisk atomubåt. Du ger skrivna order och besättningen
rapporterar. Fienden syns aldrig direkt, bara genom sonaroperatörens bäringar
och plottlagets målrörelseanalys.

## Köra

```bash
uv run main.py                     # huvudmenyn, slumpat frö
uv run main.py --scenario kuba     # hoppa över huvudmenyn (kuba, kuba-kort, jagad, jagad-kort, sundet, sundet-in, sundet-ut, konvoj, konvoj-kort, konvoj-mot, arktis, arktis-kort)
uv run main.py --seed 4            # reproducerbart scenario
uv run main.py --tyst              # utan ljud
uv run pytest             # snabba tester
uv run pytest --slow      # alla tester
```

När ett uppdrag är slut tar Enter dig tillbaka till huvudmenyn. Där finns också inställningar (ljud, tal, slumpfrö) och en lista över alla order och ryska ord. Med ljudet på (`ctrl+t` eller Inställningar) spelar menyn egen musik, hamnen i Poljarnyj och ibland Radio Moskva; fjärrskrivaren längst ned skriver flottans meddelanden fram mot den 28 oktober. Stäng programmet med `ctrl+q`. Sanningen (exakta positioner och TMA-lösningar) loggas
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
| Förslag | `ja` · `nej` · `förslag` · `förslag sonar` (maskin, plott, navigatör, torped, radio, vakthavande, starpom) · `annat förslag` |
| Tid | `tid 1` `tid 2` `tid 5` `tid 10` (faller till 1× vid larm); `tid 30` `tid 60` bara när starpom har befälet |
| Starpom | `starpom har befälet` (kaptenen går till hytten) · `jag har befälet` (till centralen, 40 s utan order) · `lägesrapport` (ring centralen) · `svara` (eller Enter i hytten när det ringer) · `sov` (60× tills starpom väcker) · `väck mig 04:30`. Order per telefon verkställs och starpom behåller befälet |
| Sonar | `aktiv sonar` (ger avstånd men avslöjar oss) |
| Plott | `läge S-1` · `plot S-1` |
| Navigation | `position` · `fix` (periskopdjup) · `kurs mot <plats>` · `följ S-1` (i kontaktens kölvatten) · `anfall S-1` (till skjutläge 1,2 nm från målets väg, efter konvojens baskurs om plottet har den) · `ekolod` · `isekolod` · `vak` (gå till och stoppa under en loggad öppning i isen) · `drivstationen` (styr mot Nord-7) · `botten` (lägg oss stilla på botten; `djup` eller `fart` lättar) · `bottenfix` (nio lodningar på tre minuter jämförs med sjökortets djup) |
| Maskin | `smygmotor` · `turbin` · `stäng reaktorn` · `starta reaktorn` · `nödblåsning` · `maskin` · `ventilera` (periskopdjup i öppen luft) |
| Vakthavande | `periskop` (svep runt, 15 s) · `periskop 047` eller `periskop S-3` (kort titt, ±16°, kortare tid med masten uppe) · `periskop upp` (står uppe tills `periskop ned`; `vrid periskop 047` vrider okularet) · i ytläge med folk på bryggan tittar vakthavande med kikaren i stället, utan mast och fartgräns · `radar` (periskopdjup; radarvarnaren är automatisk) · `foto` (periskopfoto av ankarplatsen) |
| Radio | `sänd rapport` (periskopdjup, kan pejlas) · `radio` |
| Torped | `tuber` · `torpeder` · `skjutlösning S-1` · `eld tub 1 mot S-1` · `salva S-1` eller `eld tub 1-3 mot S-1` (raka torpeder i solfjäder efter lösningens osäkerhet) · `eld tub 1 kurs 045` · `ladda tub 7 SET-53` · `skenmål` |
| Ljud | `ctrl+t` eller `ljud` / `ljud av` / `ljud på`: besättningen talar (macOS-rösten Alva, de ryska fraserna med Milena om den finns), larmen går det sonaren hör spelas i stereo (babord till vänster) och båten låter: reaktor, turbin, skrov, is, brand och kontakternas propellrar |
| Vyer | `Tab` växlar logg → sjökort → sonar → ubåten → periskopbild → logg; med tornluckan öppen kommer bryggan före periskopbilden; `Esc` eller `logg` går tillbaka till loggen. Orden `sjökort`, `sonar` (eller `vattenfall`), `ubåt` (eller `profil`, `system`), `periskopbild` och `brygga` öppnar en vy direkt; `telegram` öppnar loggboken med bara telegrammen (ordern, stabens radiogram och Radio Moskva, som också står som remsor i loggen), och mellanslag växlar till hela loggen. Order kan ges i alla vyer: varje vy har en orderrad, som också visar ett väntande förslag (`ja`/`nej`). Vyns tangenter (pilar, `+`/`-`, mellanslag, `Esc`) styr vyn när orderraden är tom; har den text redigerar de texten och `Esc` tömmer den. I periskopbilden hissar ↑ periskopet och ↓ fäller det; medan det är uppe vrider ← → okularet 5° och mellanslag vänder det förut, när det är nere byter ← → föremål i okularet, och med bryggan bemannad visar periskopbilden bryggans kikare mot det bryggvyn tittar på; på bryggan vrider ← → blicken 15° och mellanslag tittar rakt förut igen; i sonarvyn (vattenfallet: bäring mot tid, bara det sonarrummet hört) vrider ← → 30°, `+`/`-` byter tidsfönster (10, 30, 60 min), ↓ växlar sann och relativ bäring, ↑ döljer eller visar plottets lösning (på från början) och mellanslag sätter norr (eller fören) i mitten |
| Sjökort | Navigatörens sjökort i helskärm; `+`/`-` zoomar, pilarna flyttar, mellanslag centrerar |
| Ubåten | Djupprofilen och systemtavlan i en vy: genomskärningen överst, profilen till vänster och panelerna till höger (i smala fönster under profilen). Panelerna med varning och fara står först; lugna paneler samlas på en rad när det är trångt. Tavlan: ubåtens system: genomskärning av de nio avdelningarna (brand, rök, skador, reaktorns läge, vatten i kölsvinet), maskin (reaktor, framdrivning, batteri, tryckluft, skrov, vatten, koldioxid, rök), skador och reparationer per komponent, navigation, torpedtuberna med laddning, sonar och samband. Allt ur besättningens egna instrument; ▲ varning, ■ fara |
| ↳ djupprofilen | Visar ubåten från sidan över tid: vårt djup, beordrat djup, ytan, periskopdjup, språngskiktet, prov- och krossdjup, isen ovanför, botten där ekolodet lodat och det sonar hört; `+`/`-` djupskala, pilarna tidsskala, mellanslag automatisk skala. Djupmätaren till höger om loggen visar samma sak i kort form |
| Övrigt | `hjälp` · `avbryt uppdraget` (vakthavande frågar, `ja` avbryter med slutrapport) · `ctrl+q` stänger programmet |

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
| Bryggan | I ytläge öppnas tornluckan och utkikarna går upp (20 s). De ropar ut fartyg, flyg och ljus med bäring och ett grovt avstånd bedömt med ögat, och plottet får en observation per fartyg och minut. Före dykning måste bryggan utrymmas och luckan stängas, cirka 20 sekunder. Från bryggan syns också land, plask och vattenpelare från sjunkbomber, explosioner och spåret efter en ångtorped. Vyn `brygga` visar utsikten. |
| Navigering | Besticket driver med ström och loggfel; fix kräver periskopet. |
| Havsbotten | Botten varierar: vid Kuba en bank på 120–200 m längs ena sidan, ett undervattensberg och en ränna i djuphavet; i Arktis en rygg vars krön når cirka 1 000 m. Sjökortet har djupkurvor från ett gammalt kort, förskjutna och utjämnade, och ibland saknas berget. Ekolodet (`ekolod`) ger det verkliga djupet men hörs. Går vi in i botten i mer än 2 knop går vi på grund: skador på skrov, sonar eller roder och läckor i högre fart. Navigatören varnar när kortet eller en färsk lodning visar grundare vatten framåt, och osäkrare ju äldre besticket är. Grundare än provdjup kan vi lägga oss stilla på botten (`botten`): maskinen stoppas, kylpumparna går på lågvarv och jagarens eko drunknar i bottenekot. Sand och lera är mjuka; klippbotten (berg, ryggar, branta sluttningar) skrapar skrovet. Bottentypen står på sjökortet, som kan ha fel. Navigatören föreslår det när vi är jagade över grunt, mjukt vatten. Fix mot botten (`bottenfix`) går utan periskop, även under isen: nio lodningar i minst två knop matchas mot kortet. Längs en rak sluttning ger det bara en lägeslinje, vid ett berg eller en ränna läget i båda led, och aldrig bättre än kortet (0,5 nm vid Kuba, 0,8 i Arktis). Saknar kortet något säger navigatören det och låter besticket vara. Lodningarna hörs. |
| Radio | Sambandstillfällen på antenndjup (tider beror på scenariot). Sändning pejlas. |
| Starpom och hytten | Förste officeren (старпом) kan hålla befälet medan kaptenen vilar. Han beslutar om besättningens förslag inom ett fast mandat: kurs, fart, djup, smygmotor, periskop, fix, ventilera, skenmål och omladdning. Ordern kan vidga det: är uppdraget ett anfall går han själv mot skjutläget (`anfall S-x`). Han väger förslagen mot ordern och säger nej till det som skulle bryta anfallet eller följandet (t.ex. plottets TMA-gir) eller ta oss under antenndjup när ordern kräver en rapport; larm och jakt går alltid före. Avfyring, radiosändning, ytläge och att avbryta uppdraget är alltid kaptenens; då ringer han. Före skjutläget, och när ett stort fartyg är inom 3,5 sjömil med en anfallsorder, ropar han kaptenen till centralen i tid. Han väcker på tre sätt: lampan på snabbtelefonen lyser (civil kontakt), telefonen ringer (ny hotkontakt, konvoj, telegram, förslag utanför mandatet, tidsgränsen nära; svarar ingen inom 20 s knackar ordonnansen) och vid fara ropar högtalaren kaptenen till centralen (sjunkbomber, torped, skada, jakttecken). Vyn `hytt` visar kojen, repeatrarna för kurs och djup, klockan och telefonen; centralens rapporter står i loggboken men hörs inte där, och båten låter dämpad genom skottet. |
| Kvadrat 7, kort (`kuba-kort`) | Vakthavande har gått på smygmotor i en kvart och plottat en jagare som patrullerar 3–4 sjömil bort. Sambandstillfället öppnar fem minuter efter att ni tagit befälet och står öppet en kvart. Ordern kräver att rapporten sänds (`sänd rapport`, periskopdjup, 30 sekunder, och sändningen pejlas). Radiooperatören föreslår att vi väntar på djupet så länge plottet har jagaren närmare än fem sjömil, och föreslår antenndjup och sedan sändningen när den gått längre bort och ingen har oss. När fönstret stänger får jagaren inte ha kontakt med er (en pejling av sändningen räknas inte). Flyget kommer efter 5–10 minuter. Omkring 25 minuters spel. |
| Jagade (`jagad`) | Spelet börjar mitt i jakten, kl 00:40: en jagare har just fått kontakt på 2–3 sjömil och en till kommer söderifrån. Jagarna delar sina fix över radio. Efter tre anfall med signalsjunkbomber går de över till skarpa. Smyga hjälper inte när de redan har oss: djupt och fort, och sväng när de går in för anfall, för skrovsonaren ser inte rakt ned och efter detonationerna är den döv en minut. Målet är att lämna kvadrat 7 (en sjömil utanför kanten, längre följer jagarna inte efter) utan att någon jagare eller något plan har kontakt. Navigatören föreslår kortaste vägen ut som inte leder mot en hotkontakt, och banken på ena sidan ger möjlighet att lägga sig på botten. Flyget kommer efter 25–45 minuter. |
| Jagade, kort (`jagad-kort`) | Samma natt, men jagaren fäller redan skarpa sjunkbomber och går in för nästa anfall på en och en halv sjömil. Kvadraten är liten (7 sjömil) och vi ligger 2–2,5 sjömil från djupvattensidans kant, men den andra jagaren kommer in från just det hållet. Plottet ber inte om kursändringar för sin plottning medan vi är jagade. Tiden är ute efter 30 minuter. Omkring 25 minuters spel. |
| Sundet (`sundet`) | Guantánamo, 04:20, gryning 06:10. In mot inloppet från havet: en patrullbåt håller en skärm på djupt vatten 1,5–2,5 sjömil ut, hydrofoner ligger på botten en halv sjömil ut och ett nät spärrar farleden. Grinden i nätet öppnas när ett fartyg ska igenom; periskopet ser bojarna och om grinden är öppen. Patrullbåten eskorterar fartyg på väg in fram till grinden. Den som följer tätt efter ett fartyg (`följ S-3`: navigatören styr på kontaktens bäring och håller plottets fart) göms i dess brus och kölvatten och kommer in genom grinden; ut kommer man på samma sätt. Fotografera ankarplatsen (`foto`, dagsljus, ju närmare desto bättre bild; god bild krävs) och ta er ut. `kurs mot ankarplatsen` / `kurs mot nätet` styr mot kända platser. Navigatören föreslår ett väntläge utanför nätet, vid sidan av farleden (`väntläget` går dit och håller läget); vad som händer när ett fartyg kommer är kaptenens sak. Tidvattnet sätter in och ut i farleden; navigatören räknar med tabellen, som har fel. Nära land tar navigatören fix på landmärken på en halv minut. På grunt vatten dränks aktiv sonar av efterklang. |
| Sundet, grinden (`sundet-in`) | 06:30, efter gryningen. Vakthavande har legat i väntläget utanför nätet på smygmotor i tio minuter, och ett fartyg på väg in passerar om några minuter. Målet är bara en god bild av ankarplatsen; vägen ut ingår inte. Vad som görs när fartyget kommer är kaptenens sak. Tiden är ute efter 35 minuter. Omkring 25 minuters spel. |
| Sundet, ut med filmen (`sundet-ut`) | 07:00. Vakthavande har tagit bilderna av ankarplatsen och ligger innanför nätet, vid sidan av farleden på 20 meter. Ett fartyg på väg ut passerar om några minuter och grinden öppnas för det. Ute räknas en sjömil söder om nätet, förbi hydrofonerna, när ingen har er. Hur ni tar er ut är kaptenens sak. Tiden är ute efter 30 minuter. Omkring 20 minuters spel. |
| Konvojen (`konvoj`) | 28 oktober, kriget har börjat. 06:30, just efter gryningen. En konvoj med två trupptransporter och ett tankfartyg kommer från nordost med två eskortjagare i skärm 2,5 sjömil framför. Den sicksackar kring en baskurs. Ordern ger ungefär läge och kurs. Plottet grupperar kontakterna till en konvoj och räknar ut baskursen ur benen; det går mycket bättre med periskoptittar, för utkiken bedömer kursen ur vinkeln på bogen. `anfall S-x` tar oss till skjutläge vid sidan av konvojens väg; `salva S-x` skjuter raka torpeder i solfjäder. Besättningen föreslår periskopdjup och korta tittar när sonar hör stora fartyg, och navigatören föreslår anfallet när vi ligger framför; när och vad som skjuts bestämmer kaptenen. Eskortjagarna fäller skarpt direkt men släpper jakten när konvojen gått vidare; bara en i taget jagar. Målet är att sänka minst ett fartyg och sedan bryta kontakten. Neutral trafik finns kvar. |
| Konvojen, kort (`konvoj-kort`) | Samma läge, men vakthavande har redan gått på periskopdjup i 35 minuter och tittat var fjärde minut. Ni tar befälet 07:05 med konvojen 5–9 sjömil bort, plottet har grupperat den och eskorten har inte hittat er. Vakthavande ger en lägesrapport när ni tar över. Tiden är ute 45 minuter senare. Omkring en halvtimmes spel. |
| Konvojen, motanfallet (`konvoj-mot`) | Vakthavande har gått på periskopdjup när konvojen var nästan tvärs, tittat varje minut och skjutit en salva. Ni tar befälet när torpederna är framme om ungefär en minut, och en eskort har redan sett torpedbanorna och vänder mot er. Eskorterna följer en anfallen konvoj längre än vanligt (6 sjömil). Målet är att bryta kontakten: ingen eskort får ha er tio minuter efter sänkningen. Missar salvan har uppdraget misslyckats. Tiden är ute 30 minuter efter överlämnandet. Omkring 20 minuters spel. |
| Arktis: Nord-7 | Drivstationen driver med isen. Huvudstaben ger en ungefärlig position; generatorn hörs på några sjömil och ljuset syns i periskopet. Målet är ytläge inom 1,5 sjömil. En amerikansk atomubåt hör oss före vi hör den och skuggar oss, men skjuter inte. |
| Arktis, kort (`arktis-kort`) | Vakthavande har gått mot Nord-7 under isen i tjugo minuter på 60 meter, och iskartan har några öppningar bakom er. Stationen ligger ett par sjömil fram, en amerikansk ubåt är på väg dit, och branden i turbinrummet kommer inom en kvart. Målet är detsamma: ytläge inom en och en halv sjömil från stationen. Tiden är ute efter 35 minuter. Omkring 25 minuters spel. |
| Brand och rök (arktis) | En brand i turbinrummet stoppar turbinen. Röken stiger tills vi ventilerar i öppen luft och sänker besättningens förmåga; för tät rök kväver besättningen. |
| Isljud (arktis) | Bakgrundsbruset beror på isen. Skruvis knakar och kan först tas för en kontakt. |
| Packis (arktis) | Masterna kräver öppet vatten. Isekolodet lodar isen ovanför och navigatören loggar öppningar; deras läge blir osäkrare när isen driver. Kölar når 45 m: gå djupt i fart. Tunn is (≤ 1 m) kan brytas igenom i låg fart om råken är minst 120 m. Arktiskt hav saknar språngskikt; djupt gående hör och hörs längre. |
| Civil trafik (Kuba) | Handelsfartyg går genom kvadraten i tre leder; sovjetiska fraktfartyg mot Kuba stoppar när jagaren kommer nära och vänder hem. De hörs som okända kontakter tills sonar klassat dem. Deras brus kan dölja oss: under ett handelsfartyg (inom ett par kabellängder, grundare än 100 m) drunknar vårt eko i dess kölvatten. Att sänka ett civilt fartyg avslutar patrullen, och torpedrummet frågar en gång innan det skjuter mot något som inte är säkert klassat som örlogsfartyg. |
| Ubåtsjaktflyg (Kuba) | Ett patrullflygplan kommer efter 40–80 minuter och stannar en dryg timme, sedan nästa. Det hörs inte under vattnet. Radarvarnaren hör flygradarn och periskopet ser planet i dagsljus. Flyget ser master och ubåt i ytläge på radarn, fäller sonobojar (sonar hör plasken, och en aktiv boj pingar från en fast punkt) och flyger lågt med magnetisk spaning: djupare än cirka 190 meter går det rakt över oss utan utslag. Det flyget hittar får jagaren, och flyget går dit jagaren tror att vi är. |
| Torpeder | 53-61 (rak, snabb), SET-53 (målsökande), T-5 (kärnladdning, spärrad utan order). Avfyring från högst 100 m djup och i högst 12 knop. |
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
  scenario/          scenarier (en modul per scenario, common) och registret
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
  periscope.py       periskopbilden: synlig del, vinkel på bogen, lanternor (kunskap)
  convoy.py          SANNING: konvojens ledpunkt, sicksack, formation och nödgir
  stations/          ett system ombord per modul
    base.py          Station: COMMANDS, on_order, update, say, suggest
    navigation/      kurs, fart, djup, bestick, fixar (tasks.py), ekolod, is, styruppdrag, väg ut
    engineering.py   maskin och skadekontroll
    sonar_room.py    sonar, transienter, aktiv sonar
    officer.py       radar, radarvarnare, kamera
    starpom.py       starpom har befälet: mandat, väckning, kaptenens väg till centralen
    periscope.py     periskopet i realtid: svep, titt, hålläge
    bridge.py        tornluckan och utkiken på bryggan i ytläge
    radio.py         sambandstillfällen och rapporter
    plot.py          plottlaget
    torpedo_room.py  torpedrum och eldledning
ui/                  Textual
  audio.py           tal, larm och hydrofonljud (say/afplay)
  ambience.py        bakgrundsljud: mixer och slingor (sounddevice)
  chart.py           sjökortet i helskärm
  chart_render.py    rastrering av sjökortet till tecken
  boat.py            vyn Ubåten i helskärm (djupprofil och systemtavla)
  boat_render.py     vyns layout efter fönstret
  cabin.py           kaptenens hytt medan starpom har befälet
  cabin_render.py    kojen, repeatrarna, Kasjtan-telefonen och gången till centralen
  strips.py          telegramremsor i loggboken (ordern, staben, Radio Moskva)
  profile_render.py  rastrering av djupprofilen och djupmätaren
  systems_render.py  genomskärning och paneler till tecken
  periscope.py       periskopbilden i helskärm (utkikens senaste svep)
  periscope_render.py remsa, okular och siluetter till tecken
  bridge.py          utsikten från bryggan i helskärm (utkikens bild, varannan sekund)
  bridge_render.py   himmel, sjö, fördäck och kölvatten, föremålen med periskopets siluetter
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
   `system_items()`; en ny panel dyker upp i vyn Ubåten av sig själv.
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
