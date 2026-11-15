# K-114 – idéer och förbättringar som inte är byggda

Samlat 2026-11-15 ur tidigare samtal. Inget av detta är beställt; varje punkt väntar på
kaptenens (användarens) beslut. Det som redan är byggt står i CLAUDE.md och README.md.

## Öppna fel och osäkra siffror

- ~~Plottet kallar ibland felaktiga lösningar "god"~~ – rättat 2026-11-15 (manöverbrus, gamla
  lösningar, kursen som tak). Kvar: girar de senaste minuterna innan plottet sett dem (~9 % grova fel).
- **Torpedrummet säger skjutlösning på bevakningsfartyget** före torpedsteget i övningen.
- ~~Kalibreringssiffror som glidit~~ – alla botar omkörda 2026-11-15 och siffrorna rättade i
  CLAUDE.md. Störst skillnad: Kvadrat 7 hittas nu av jagaren i 12 av 12 (angivet 9) och flyget 11
  av 12 (8); konvoj-mot passiv/ja 5 av 8 (3/4). Inte omkört: sundet med sanningsboten, väntläget.
- **Gränssnittet ej provkört för hand** i riktig terminal: övningen, periskopet i realtid.
- **Konvojen:** ska besättningen föreslå en periskoptitt strax före skjutläge? Boten skjuter
  på gamla lösningar (titt var 4:e min, ben på 5–10 min).

## Arkitektur (granskning 2026-11-15, "inte nu")

Grunden håller (sanning/kunskap isär, determinism, `sim/` utan Textual, rapporter som data,
stationer som plugin). Förbättringar i prioritetsordning:

1. **Målobjekt:** `World._check_outcome` är en växande if-kedja över otypat `mission`-dict
   (~50 nycklar). Låt scenariot bära `Goal`-objekt med `check(world)`. Blir dyrare för varje
   nytt scenario.
2. ~~Kalibreringsbotarna in i repot~~ – gjort 2026-11-15, se `kalibrering/`. Kvar: köra om
   siffrorna i CLAUDE.md med dem.
3. **Dela `navigation.py`** (~2 250 rader) i delmoduler, och `scenario.py` (~1 200) till paket.

Mindre: importtest som vaktar att kunskapsmoduler inte importerar `world`/`entities`; talet
är bundet till macOS `say`.

## Gränssnitt och grafik (granskning 2026-11-15, "inte nu")

Centralen (braille) håller högst nivå; övriga vyer ritar med hela tecken.

**Största luckan: sonarvy med vattenfall** – bäring mot tid, plottets lösning ovanpå
(`Station.sonar_items()` + braillerenderare). Föreslagen först.

**Snabba fixar:**
- Sjökortet: hackiga linjer (`|/\`), djupkurvor som lodräta streck liknar spår, etiketter krockar.
- Periskopet: okularet svart på dagen (tona himmel/hav), avståndsskala saknas; ingen förstoring
  (1,5×/6×).
- Bryggan: land ritas som block med mörka ränder (ser ut som fel); sjögång saknas.
- Systemtavlan: tom nedre halva; kontaktlistan klipps ("S").
- Profilen: "hört"-bandet oförklarat.
- Huvudraden: kontaktlistan utan hotfärg och sortering.

**Framtidsspår med insats:**
1. Braille i sjökort, profil och brygga – liten–medel, 3–5 steg, låg risk.
2. Animering i realtid på sjökortet – medel, 3–4 steg; byggs ur kunskapen (beräknad egen
   torpedbana, fiendens torpedbäring), aldrig sanningen.
3. Bilder i terminalen (Kitty/sixel) – medel–stor, 5–8 steg, hög risk, bara vissa terminaler,
   behöver braillereserv. Prova först.
4. Webb: A) Textual Serve – 1 steg, ingen grafisk vinst, ljudet når inte webbläsaren;
   B) egen webbklient – 15–30 steg, dubbelt underhåll, `sim/` oförändrad.

Rekommendation: sonarvy, sedan 1 (+2) och småfixarna; 3 bara efter prov; 4B bara om terminalen
överges.

### Ubåtsvyn (användaren funderar)

Slå ihop djupprofil och systemtavla till en vy "Ubåten" (`BoatScreen`, orden `ubåt`/`profil`/`system`):
genomskärningen överst i full bredd, djupprofilen vänster ~60 %, panelerna höger ~40 % i kompakt
form (ok-panel = en rad, varning/fara fullt med staplar, torpedrören på en rad, fara överst).
Smalt (< ~110 kol) staplat; lågt (< ~25 rader) avdelningarna som lampor i huvudet.
Tab: central → logg → sjökort → ubåten → brygga → periskopbild.
Steg: `render_panels(compact=True)` → `BoatScreen`/Tab/`VIEW_WORDS` → skärmdumpar.
Öppet: namnet (Ubåten/Dykning) och om de gamla vyerna tas bort (förslag: ja).

### Centralen, parkerade steg

- **C3 besättningen:** större figurer med namn, pratbubblor, förslag i gult, snabbtelefonen
  med Volkov/Belov/Ivanov; rorsmän Sidorov och Gusev (ej bekräftade). Obs: figurerna togs bort ur
  stora bilden efter C2 – stäm av på nytt innan.
- **C4:** reaktorpanel, julgranen som rutnät, bäringsrepeater ur kunskapen, periskopokular som vrids.

### Huvudmenyn

- **M4 tjänsteblad:** spelade uppdrag med utfall, datum och frö sparade i fil mellan körningar.

## Spelidéer

Favoriter först:

1. **Kärnvapenbeslutet** (B-59/Archipov): skarp T-5 kräver tre officerares samtycke (kapten,
   zampolit, andre kapten). Zampoliten är förberedd i `events.py` men obyggd.
2. **Besättningen som människor:** trötthet och vaktskiften, personligheter (ängslig navigatör,
   ivrig torpedofficer), moral som påverkar förslag, ibland fel klassning. Krokarna finns
   (`effective_skill`, rapportfilter).
3. **Kampanj Oktober 1962:** uppdrag i följd där skador, torpeder och trötthet följer med,
   historiska händelser ändrar ordern, slutrapporten som bedömning (medalj/krigsrätt).

Övrigt:
- Order som krockar med läget; reaktor av/batteri-scenario; osäkert neutralt mål.
- Viskningar och skrovknak under jakt; "torped i vattnet"-nedräkning.
- Slumpade kriser; jagarkaptener med personlighet; svårighet via besättningens kunskap.

## Scenarier

- **Duellen under isen** (Nord-3, krig): vapen tillåtna, US-ubåten öppnar torpedrör på 9 nm.
  Mål: sänka den eller ta sig ut. Kräver att `SubmarineAI` (`sim/arctic.py`) kan skjuta (roe,
  egen lösning, undanmanöver) och fiendetorpeder som söker mot oss. Rekommenderad som nästa.
- **Haveri** (K-19-inspirerat): läcka i primärkretsen vid start, fart ≤ 6 kn, strålning per
  avdelning, jagare ovanför. Mål: hålla reservkylningen och nå bärgningsfartygets mötesplats
  oupptäckt. Kräver reaktorstation (temperatur, kylning, strålning som sänker `effective_skill()`
  som röken); systemtavlan blir huvudvy.
- **Räddningen:** havererad sovjetubåt.
- **Spaningen:** spela in amerikanska ljud.

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
scenarier, astronavigering, torpedomladdning, ljuskulor.

Vyer: sonarvattenfall, plottbord, eldledning, trimtavla, besättningslista, hydrologi.

Periskopet ser ännu inte land eller händelser (bara bryggan gör det).

## Realismluckor mot Projekt 627A

- Två reaktorer, två turbiner, två axlar.
- Primärkrets och strålningsdos per avdelning.
- Trim och barlast; turbogeneratorer och nöddiesel; hydraulik.
- Syre och regenereringspatroner; vaktschema.
- Astronavigering; tröghets- och radionavigering i Arktis.
- Signalspaning av fiendens ping; sambandsschema och långvåg.
- Minor; nödutrymning.

Historiska anmärkningar: Kuba-ubåtarna 1962 var Projekt 641 (diesel), inte 627A. Provdjup
300 m och krossdjup 450 m är troligen generöst (källor anger ~240/300 m). K-3 nådde Nordpolen
juli 1962. 627A-båtarna låg 1962 i Zapadnaja Litsa; övningen utgår ändå från Poljarnyj
(medvetet val).
