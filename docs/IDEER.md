# K-114 – idéer och förbättringar som inte är byggda

Samlat 2026-11-15 ur tidigare samtal, uppdaterat 2026-11-17. Inget av detta är beställt; varje punkt
väntar på kaptenens (användarens) beslut. Det som redan är byggt står i CLAUDE.md och README.md.

## Öppna fel och osäkra siffror

- ~~Plottet kallar ibland felaktiga lösningar "god"~~ – rättat 2026-11-15 (manöverbrus, gamla
  lösningar, kursen som tak). Kvar: girar de senaste minuterna innan plottet sett dem (~9 % grova fel).
- ~~Torpedrummet säger skjutlösning på bevakningsfartyget före torpedsteget~~ – rättat 2026-11-16
  (`TorpedoExercise` ⇒ `Knowledge.torpedo_exercise`).
- ~~Kalibreringssiffror som glidit~~ – alla botar omkörda 2026-11-15 och siffrorna rättade i
  CLAUDE.md. Störst skillnad: Kvadrat 7 hittas nu av jagaren i 12 av 12 (angivet 9) och flyget 11
  av 12 (8); konvoj-mot passiv/ja 5 av 8 (3/4). Inte omkört: sundet med sanningsboten, väntläget.
- **Gränssnittet ej provkört för hand** i riktig terminal: övningen, periskopet i realtid, ubåtsvyn,
  hyttvyn (färgerna), sjökortets blyertsmärken.
- **Konvojen:** ska besättningen föreslå en periskoptitt strax före skjutläge? Boten skjuter
  på gamla lösningar (titt var 4:e min, ben på 5–10 min).
- **Konvojen med starpom:** ett neutralt fartyg sänkt i en körning med salvaboten (troligen botens
  fel, inte utrett).
- **Sjökortet:** i en jaktkörning (`jagad-kort`, frö 2) fick bara den ena jagaren märket "först hörd";
  den andra fick troligen sin beteckning på annat sätt än genom sonarens upptäckt. Inte utrett.
- **Ubåtsvyn:** profilen får 60 % även när den är tom (stor tom yta i 150 kolumner).
- **Hytten:** mitten är tom i stora fönster.

## Arkitektur (granskning 2026-11-15, "inte nu")

Grunden håller (sanning/kunskap isär, determinism, `sim/` utan Textual, rapporter som data,
stationer som plugin). Förbättringar i prioritetsordning:

1. ~~Målobjekt~~ – gjort 2026-11-16: `sim/goals.py`, `World.goals`. `mission` håller bara det
   som hänt (sänkt, foto, rapport, grundstötning, räknare).
2. ~~Kalibreringsbotarna in i repot~~ – gjort 2026-11-15, se `kalibrering/`.
3. **Dela `navigation.py`** (~2 400 rader) i delmoduler, och `scenario.py` (~1 200) till paket.

Mindre: ~~importtest~~ (gjort 2026-11-16, `tests/test_import_boundaries.py`); talet är bundet
till macOS `say`.

## Gränssnitt och grafik

Granskning 2026-11-15. Byggt sedan dess: braille i sjökort, profil, genomskärning, brygga och
periskopets okular (2026-11-17), ubåtsvyn (djupprofil + systemtavla, 2026-11-16), plottlagets
blyertsmärken på sjökortet (B1–B3, 2026-11-17; valt i stället för animering, se nedan).

~~**Sonarvy med vattenfall**~~ – byggd 2026-11-17 (S1–S5, se CLAUDE.md). Kvar att pröva: om
lösningskurvan ska vara på som standard, och om vyn behöver ett läge med bara hot. Ej provkörd
för hand i riktig terminal.

**Snabba fixar kvar:**
- Periskopet: avståndsskala saknas.
- Bryggan: sjögång saknas.
- Systemtavlan: kontaktlistan klipps ("S").
- Profilen: "hört"-bandet oförklarat.
- Huvudraden: kontaktlistan utan hotfärg och sortering.

**Framtidsspår med insats:**
1. ~~Braille i sjökort, profil och brygga~~ – byggt 2026-11-17.
2. ~~Animering i realtid på sjökortet~~ – ersatt av blyertsmärken (ett papperskort och
   автопрокладчик är realistiskt; vidgade ringar, blixtar och mjuk förflyttning är det inte, och
   en braillepunkt är 0,05 nm, så mjuk förflyttning syns inte). Föreslå inte igen.
3. Bilder i terminalen (Kitty/sixel) – medel–stor, 5–8 steg, hög risk, bara vissa terminaler,
   behöver braillereserv. Prova först.
4. Webb: A) Textual Serve – 1 steg, ingen grafisk vinst; B) egen webbklient – 15–30 steg, dubbelt
   underhåll, `sim/` oförändrad.

### Periskopets förstoring (2026-11-16, "avvakta")

- **Z1** låg/hög förstoring (32°/8° synfält), bedömningens σ efter förstoringen.
- **Z2** besättningen växlar själv: svep i låg, titt i hög.
- **Z3** siluetten skalad efter vinkelstorleken (braille).
- **Z4** kikaren på bryggan 7×.

Periskopet ser ännu inte land eller händelser (bara bryggan gör det). Ingen däckskanon (627A hade
ingen; föreslå inte).

### Centralen, parkerade steg

- **C3 besättningen:** större figurer med namn, pratbubblor, förslag i gult, snabbtelefonen
  med Volkov/Belov/Ivanov; rorsmän Sidorov och Gusev (ej bekräftade). Obs: figurerna togs bort ur
  stora bilden efter C2 – stäm av på nytt innan.
- **C4:** reaktorpanel, julgranen som rutnät, bäringsrepeater ur kunskapen, periskopokular som vrids.

### Huvudmenyn

- **M4 tjänsteblad:** spelade uppdrag med utfall, datum och frö sparade i fil mellan körningar.

### Dockikonen (2026-11-17, "avvakta")

K-114.app (nu i `~/projekt/`) är ett AppleScript som startar spelet i Terminal, så Docken visar
Terminals ikon. Vägar:
1. **Eget fönster (rekommenderat):** `textual-serve` på `localhost` och ett `pywebview`-fönster,
   ikonen satt med `NSApplication.setApplicationIconImage_`; valfria beroenden, ett kort
   startskript (`fonster.py`), appen byggs om. Ljudet fungerar (Python spelar det lokalt). Prova:
   braille och radavstånd i xterm.js, att Tab/Esc/ctrl+t når spelet, centralen i 10 Hz, ⌘Q.
2. Appen står kvar medan spelet körs: ubåtsikonen bredvid Terminals, inte i stället.
3. Reserv: en egen omdöpt kopia av Alacritty/WezTerm med K-114-ikonen (påverkar inte den vanliga
   terminalen; måste laddas ner och signeras om). Ghostty med egen ikon avråds (ändrar ikonen globalt).

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

- **Duellen under isen** (Nord-3, krig): vapen tillåtna, US-ubåten öppnar torpedrör på 9 nm.
  Mål: sänka den eller ta sig ut. Kräver att `SubmarineAI` (`sim/arctic.py`) kan skjuta (roe,
  egen lösning, undanmanöver) och fiendetorpeder som söker mot oss (finns inte i spelet än).
  Rekommenderad som nästa.
- **Haveri** (K-19-inspirerat): läcka i primärkretsen vid start, fart ≤ 6 kn, strålning per
  avdelning, jagare ovanför. Mål: hålla reservkylningen och nå bärgningsfartygets mötesplats
  oupptäckt. Kräver reaktorstation (temperatur, kylning, strålning som sänker `effective_skill()`
  som röken); systemtavlan blir huvudvy.
- **Räddningen:** havererad sovjetubåt.
- **Spaningen:** spela in amerikanska ljud.

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

## Radion (parkerad, "avvakta")

1. Rapporter med innehåll ur kunskapen; sändningstid efter innehåll; pejlrisken växer med längd
   och närhet.
2. `sim/headquarters.py`: huvudstaben vet bara vad vi sänt (`ReportTransmitted`) och skriver
   meddelanden efter det.
3. Uppdragsmål i slutrapporten (rapporterat, förblev oupptäckt, ingen vapenanvändning,
   sambandstillfällen).
4. Valfritt: villkorat tillstånd för T-5 – känsligt, användarens beslut.

Framtida idé: radiospaning av amerikansk trafik vid sambandstillfällen, t.ex. i Arktis.

## Nya system och vyer

System: trim och flytkraft (torpedvikt, kompression), batytermograf och akustisk prognos,
egenbrus, luft (O₂/CO₂, regenereringspatroner), vakter och trötthet, undervattenstelefon i fler
scenarier, torpedomladdning, ljuskulor. (~~Astronavigering~~ byggd som stjärnfix 2026-11-17.)

Vyer: sonarvattenfall, plottbord, eldledning, trimtavla, besättningslista, hydrologi.

## Realismluckor mot Projekt 627A

- Två reaktorer, två turbiner, två axlar.
- Primärkrets och strålningsdos per avdelning.
- Trim och barlast; turbogeneratorer och nöddiesel; hydraulik.
- Syre och regenereringspatroner; vaktschema.
- Tröghets- och radionavigering i Arktis (astronavigering finns: stjärnfix).
- Signalspaning av fiendens ping; sambandsschema och långvåg.
- Minor; nödutrymning.

Historiska anmärkningar: Kuba-ubåtarna 1962 var Projekt 641 (diesel), inte 627A. Provdjup
300 m och krossdjup 450 m är troligen generöst (källor anger ~240/300 m). K-3 nådde Nordpolen
juli 1962. 627A-båtarna låg 1962 i Zapadnaja Litsa; övningen utgår ändå från Poljarnyj
(medvetet val).
