# K-114 – idéer och förbättringar som inte är byggda

Samlat 2026-11-15 ur tidigare samtal, uppdaterat 2026-11-18 (kväll). Inget av detta är beställt; varje punkt
väntar på kaptenens (användarens) beslut. Det som redan är byggt står i CLAUDE.md och README.md;
konkreta öppna uppgifter (köra om, prova, utreda) i `docs/TODO.md`.

## Öppna fel och osäkra siffror

Flyttade till `docs/TODO.md` (2026-11-18).

## Arkitektur

Grunden håller (sanning/kunskap isär, determinism, `sim/` utan Textual, rapporter som data,
stationer som plugin). Gjort efter granskningarna 2026-11-15 och 2026-11-18: målobjekt (`goals.py`),
kalibreringsbotarna i `kalibrering/`, importtestet, `navigation/` och `scenario/` som paket,
navigatörens uppdrag (`NavTask`, `Steering`), stationernas väg till sanningen (`REACHES_WORLD`),
slumpen per station (`rng_for`), kalibreringskontrollen (`kontroll.py`, `fingeravtryck.py`),
vyerna en gång per läge och CLAUDE.md delad i `docs/system/`.

Kvar:

- **Talet bakom ett gränssnitt** (resonerat 2026-11-18). Det finns redan en spelare (`MacPlayer`,
  `NullPlayer`, testernas `RecordingPlayer`); bundet till macOS är `say`/`afplay`, röstnamnen och
  tre kopior av `say -v ?`. Steg:
  ~~T1 rösterna på ett ställe~~ (byggt 2026-11-18: `ui/voices.py`, `MacSay`, röstlistan läses en gång);
  ~~T2 talet och effektljuden genom mixern~~ (byggt 2026-11-18: `MixPlayer`, `MacSynth`, telefon och skott,
  se `docs/system/granssnitt.md`). Underlaget:
  hytten dämpar centralen i stället för att tysta den, telefonfilter för stationerna utanför
  centralen, inga `afplay`-processer – det enda som märks på Mac, och det enda med risk (fördröjning);
  fördröjningen uppmätt 2026-11-18: `say -o` tar 0,55–0,75 s per replik oavsett längd (mest uppstart
  och röstladdning, samma som `say` i dag lär ha innan ljudet börjar); `NSSpeechSynthesizer` i processen
  med rösten laddad 20–60 ms (första gången 0,1–0,4 s). T2 bör alltså rendera i processen (pyobjc-Cocoa
  som beroende på macOS, en syntes per röst) och inte med `say -o`.
  ~~T3 piper/espeak-ng för Linux~~ – struken 2026-11-18 (kaptenens beslut: macOS räcker). Föreslå inte igen.

## Gränssnitt och grafik

Granskning 2026-11-15. Byggt sedan dess: braille i sjökort, profil, genomskärning, brygga och
periskopets okular (2026-11-17), ubåtsvyn (djupprofil + systemtavla, 2026-11-16), plottlagets
blyertsmärken på sjökortet (B1–B3, 2026-11-17; valt i stället för animering, se nedan),
periskopets förstoring och bryggans kikare, hyttens kort och krängningsmätare, ubåtsvyns
automatiska tidsskala (2026-11-18).

~~**Sonarvy med vattenfall**~~ – byggd 2026-11-17 (S1–S5, se `docs/system/vyer.md`); rättad 2026-11-18
(girmärken, relativ bäring). Lösningskurvan på från början och neutrala kontakter nedtonade
(2026-11-18) i stället för ett läge med bara hot. Ej provkörd för hand i riktig terminal.

~~**Snabba fixar**~~ – gjorda 2026-11-17 (F1–F5a): huvudradens kontakter hot först och i färg,
sonarpanelen räknar, profilens band heter "sonar hörde", utkikens avstånd i periskopbilden,
sjögång i bilden (`Environment.sea_state`).

**Sjögångens verkan (F5b, "avvakta"):** sjögången bara i bilden än så länge. Nästa steg vore
verkan: bakgrundsbrus (havsbrus efter Beaufort), utkikens sikt och bedömningsfel, flygets radar
mot master, periskopdjupet (masten sköljs över, svårare hålla djupet) och kanske slumpad sjögång
per uppdrag. Kräver ny kalibrering.

**Framtidsspår med insats:**
1. ~~Braille i sjökort, profil och brygga~~ – byggt 2026-11-17.
2. ~~Animering i realtid på sjökortet~~ – ersatt av blyertsmärken (ett papperskort och
   автопрокладчик är realistiskt; vidgade ringar, blixtar och mjuk förflyttning är det inte, och
   en braillepunkt är 0,05 nm, så mjuk förflyttning syns inte). Föreslå inte igen.
3. ~~Bilder i terminalen (Kitty/sixel) och webbklient~~ – strukna 2026-11-18 (kaptenens beslut).
   Föreslå inte igen.

### ~~Periskopets förstoring~~ (byggd 2026-11-18, Z1–Z4, se `docs/system/utkik.md`)

Byggt: låg/hög förstoring med σ efter förstoringen, svep i låg och titt i hög, upptäckt efter
vinkelstorlek och horisont, okularet efter förstoringen med stadimeterns streck, utkikens kikare 7×
och kikaren i bryggvyn. Kvar som idé: siluetter i braille skalade steglöst efter vinkelstorleken.

Periskopet ser land sedan 2026-11-18 (`_observe_land`), men ännu inte händelser (plask, vattenpelare; bara bryggan). Ingen däckskanon (627A hade
ingen; föreslå inte).

### Centralen, parkerade steg

- ~~**C3 besättningen**~~ (figurer, pratbubblor) – struken 2026-11-18 (kaptenens beslut). Föreslå inte igen.
- ~~**C4**~~ – byggd 2026-11-18: periskopokularet vrids (C4a), julgranen med alla öppningar (C4b),
  bäringsrepeatern på gyrot (C4d). Reaktorpanelen (C4c) struken: systemtavlan visar redan samma; hör
  till Haveri om primärkretsen modelleras.

### Huvudmenyn

- **M4 tjänsteblad:** spelade uppdrag med utfall, datum och frö sparade i fil mellan körningar.

~~**Dockikonen**~~ – byggd 2026-11-18 som eget fönster (`fonster.py`, textual-serve + pywebview). Kvar om spelet
ska delas: paketera till en fristående app (PyInstaller/Briefcase) och signera.

## Spelidéer

Favoriter först:

1. **Kärnvapenbeslutet** (B-59/Archipov): skarp T-5 kräver tre officerares samtycke (kapten,
   zampolit, starpom). Zampoliten är förberedd i `events.py` men obyggd.
2. **Besättningen som människor:** trötthet och vaktskiften, personligheter (ängslig navigatör,
   ivrig torpedofficer), moral som påverkar förslag, ibland fel klassning. Krokarna finns
   (`effective_skill`, rapportfilter).
3. **Kampanjen «Октябрь 1962»** (skissad 2026-11-16, "avvakta"), se nedan.

Övrigt:
- Order som krockar med läget; reaktor av/batteri-scenario; osäkert neutralt mål.
- Viskningar och skrovknak under jakt; "torped i vattnet"-nedräkning.
- Slumpade kriser; jagarkaptener med personlighet; svårighet via besättningens kunskap.

### Kampanjen «Октябрь 1962» (K1–K5)

En patrull 1–28 okt där scenarierna blir uppdrag med transiter emellan; starpom och hytten
(byggda 2026-11-16) är förutsättningen.
- **Förlopp:** avgång från Poljarnyj 1 okt (som övningens fjord), transit genom Norska havet och
  GIUK-gapet (snabbspolad; väckning vid Neptune-flyg, kontakter, dygnets sambandstillfälle),
  Atlanten där telegrammen styr (22 okt karantänen, 24 okt blockaden, sedan Kvadrat 7, Sundet eller
  Konvojen efter datum och rapporter), slutet: hemfärd eller kriget 28 okt.
- **Följer med mellan uppdragen** (JSON): torpeder och skenmål (omladdning bara i hemmahamn),
  skador som bara delvis lagas till sjöss, luft och regenereringspatroner, besättningens trötthet
  (vaktschema), kaptenens vila.
- **Vila som resurs:** en kapten som aldrig lämnar över blir trött ⇒ straff i `effective_skill` för
  vakthavande och plottet, kortare snabbspolning.
- **Beslut i transiten:** turbin (fort men hörs) eller smygmotor, sända rapport vid
  sambandstillfället (pejlbart), vidga eller snäva starpoms mandat inför natten.
- **Kampanjkarta:** Nordatlanten med vägen enligt besticket (aldrig sanningen), telegrammens
  kvadrater, datumet och fjärrskrivarremsan.
- **Slutet:** ДОНЕСЕНИЕ till staben med utfallet medalj, omplacering eller krigsrätt (upptäckt,
  neutralt fartyg sänkt, sänt för ofta). Kopplas till zampoliten och kärnvapenbeslutet 27 okt.
- **Steg:** K1 kampanjtillstånd och sparning; K2 transit med snabbspolning och händelser; K3
  telegrammen väljer uppdrag; K4 kampanjkartan; K5 slutbedömningen.

## Scenarier

- ~~**Duellen under isen**~~ – byggd 2026-11-18 (`duell`, `duell-kort`, D1–D4, se
  `docs/system/scenarier.md`).
- **Haveri** (K-19-inspirerat): läcka i primärkretsen vid start, fart ≤ 6 kn, strålning per
  avdelning, jagare ovanför. Mål: hålla reservkylningen och nå bärgningsfartygets mötesplats
  oupptäckt. Kräver reaktorstation (temperatur, kylning, strålning som sänker `effective_skill()`
  som röken); systemtavlan blir huvudvy.
- **Clyde** (`clyde`, skissat 2026-11-18): svår undervattensnavigering, se nedan.
- **Räddningen:** havererad sovjetubåt.
- **Spaningen:** spela in amerikanska ljud.

### «Клайд» – in i Firth of Clyde (`clyde`, skissat 2026-11-18)

20 okt 1962: in i Firth of Clyde i undervattensläge förbi Arran och Bute till inloppet av Holy Loch
(amerikanernas Polarisbas), spela in en Polarisubåt som går ut och kom ut oupptäckta före gryningen
(knyter an till Spaningen). Till skillnad från Sundet (foto, farleden) är navigeringen motståndet:
~40 nm från Pladda till Holy Loch och samma väg ut, mest i sund på 1–3 nm med branta stränder.
- **Varför det är svårt:** tidvattnet sätter 1–2 kn i sunden och vänder var 6:e timme; besticket räknar
  inte med strömmen och glider fortare än σ säger (ärligt fel som besättningen ska upptäcka). Varje
  periskopfix kostar (fiskebåtar, färjor, engelsk ubåtsjakt; landmärken bara i dagsljus eller fyrar).
  Bottenfixen är bra (noggrant brittiskt kort, brant botten) men tar 3 min i ≥ 2 kn. 40–150 m djupt:
  djupt gömmer men ger mindre marginal. Molnen i oktober stänger stjärnfixen.
- **Steg:**
  ~~N1~~ (byggt 2026-11-18, `navigation/current.py`, se `docs/system/hav.md`): navigatören räknar strömmen ur skillnaden mellan bestick och två fixar ("strömmen sätter 040,
  1,2 knop, osäker", kvalitet ur fixarnas σ), lägger in den i besticket och föreslår kursrättelse;
  tidvattentabellen i kunskapen (som almanackan), den verkliga strömmen avviker. Nyttig i alla scenarier.
  N2 molntäcke i `Environment` (stänger stjärnfix, mörkare nätter; rör ljusets kalibrering lite).
  N3 fyrar som landmärken (Pladda, Little Cumbrae, Toward Point): fix σ 0,1 på natten om fyren syns
  och inte skyms av land.
  N4 geografin: kust, öar och botten ur ett förenklat kort, sjökortets kopia med litet fel (0,1 nm);
  största delen.
  N5 motstånd och mål: engelska patrullbåtar, hydrofonlinje vid Cumbrae, fiskebåtar, färjan Wemyss
  Bay–Rothesay; `RecordGoal` (Polarisubåten hörd länge nog med god kvalitet), sedan `EscapeGoal`
  före gryningen och `GroundingFails`.
  N6 kort variant `clyde-in`: söder om Little Cumbrae, bestick σ 0,8 nm, strömmen på väg att vända,
  ~40 min; 8 frön enligt riktmärkena.
- **Spelkänslan:** titt (fix och risk), bottenfix (tid och fart) eller lita på besticket (σ växer,
  strömmen okänd). Besättningen säger hur säkert läget är ("läget osäkert, 0,6 nm, sundet är 1,4
  brett"); navigatören föreslår vad som behövs, `_shoal_watch` varnar.
- **Öppna frågor:** Holy Loch eller en påhittad bas (en påhittad norsk fjord vore mindre arbete i N4)?
  N1 först och fristående (billigast, nytta i Sundet och Arktis)? Tidvattnet kraftigare än verkligheten
  (Clyde mest 0,5–1,5 kn, starkast i Kilbrannan Sound)?

### Avhopp till västmakterna (`avhopp`, skissat 2026-11-16, "bra men avvakta")

24 okt 1962, 22:40: kaptenen hoppar av från Kolafjorden till norskt territorialvatten vid Vardø
(4 nm 1962, kontrollera), ~60–70 nm. Medvetet olik Röd Oktober: ingen hemlig drivning, ingen
konspiration, ensam kapten. Tre motståndare:
- **Besättningen:** zampolit och osobist med misstanke (bara sanning) som stiger vid avvikelse från
  ordern och sjunker med tiden: lojal → frågar → misstänker → agerar (osobisten sänder på antenndjup /
  myteri `mutiny`). Spelaren ser tecken; `förklara gyrofel/ubåtsjakt` vars trovärdighet räknas ur
  egna instrument (aldrig slump). Rapportfilterkroken.
- **Staben/Norra flottan:** vet bara vad vi sänt (radions steg 2); missade sambandstillfällen ⇒
  telegram, sedan SKR + Be-6 mot senast kända läge.
- **Väst:** norska patrullbåtar, P-2 från Andøya skuggar. Signalera: undervattenstelefon (≤ 5 nm,
  sovjeter hör), signallampa från bryggan, klartext på nödfrekvens (pejlas). Tidigt eller sent;
  antenndjup ger osobisten chansen.
- Mål `DefectGoal`; utfall mutiny, sänkt, defection_failed, returned. Navigatören är den ende
  invigde och föreslår vägen; övriga föreslår efter ordern.
- Kort variant `avhopp-ut`: 25 nm från Vardø, ett sambandstillfälle missat, SKR 8 nm bakom, 40 min.
- Steg: A1 kust och mål, A2 staben, A3 zampolit och osobist, A4 väst och signalerna, A5 kort variant
  + 8 frön.
- Öppna frågor: kaptenen eller en annan avhoppare; motivet (outsagt, personligt, vägrar T-5); staben
  via radioomdesignen eller förenklad.

## ~~Radion~~ (byggd 2026-11-19, R1–R6, se `docs/system/besattning.md`)

Byggt: rapporter med innehåll ur kunskapen och sändningstid efter längd (R1), pejlrisk efter längd
(R2), huvudstaben som bara vet vad vi sänt (R3), sambandet i slutrapporten (R4), villkorat tillstånd
för T-5 i jagad (R5), radiospaning (R6). Kvar som idé: stabens svar som styr nästa uppdrag i en
kampanj (`Headquarters.received` sparar det vi rapporterat), zampolitens samtycke till T-5
(kärnvapenbeslutet).

## Nya system och vyer

System: ~~trim och flytkraft~~ (byggt 2026-11-18, TR1–TR4, se `docs/system/besattning.md`), batytermograf och akustisk prognos,
egenbrus, luft (O₂/CO₂, regenereringspatroner), vakter och trötthet, undervattenstelefon i fler
scenarier, torpedomladdning, ljuskulor. (~~Astronavigering~~ byggd som stjärnfix 2026-11-17.)

Vyer: ~~sonarvattenfall~~ (byggt), eldledning, ~~trimtavla~~ (i ubåtsvyn: panelen TRIM och tankarna i
genomskärningen, 2026-11-18), besättningslista, hydrologi.
~~Plottbord~~ som egen vy strukits 2026-11-18: sjökortet är redan plottbordet. ~~Bäringslinjerna för ett
markerat mål~~ byggda 2026-11-18 (solfjädern, `plot S-1`).

## Realismluckor mot Projekt 627A

- Två reaktorer, två turbiner, två axlar.
- Primärkrets och strålningsdos per avdelning.
- ~~Trim~~ (byggt); huvudbarlasten bara som regel (ytläge, lodrät djupändring); turbogeneratorer och nöddiesel; hydraulik.
- Syre och regenereringspatroner; vaktschema.
- Tröghets- och radionavigering i Arktis (astronavigering finns: stjärnfix).
- Signalspaning av fiendens ping; sambandsschema och långvåg.
- Minor; nödutrymning.

Historiska anmärkningar: Kuba-ubåtarna 1962 var Projekt 641 (diesel), inte 627A. Provdjup
300 m och krossdjup 450 m är troligen generöst (källor anger ~240/300 m). K-3 nådde Nordpolen
juli 1962. 627A-båtarna låg 1962 i Zapadnaja Litsa; övningen utgår ändå från Poljarnyj
(medvetet val).
