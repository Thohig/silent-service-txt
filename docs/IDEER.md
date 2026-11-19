# K-114 – idéer och förbättringar som inte är byggda

Samlat 2026-11-15 ur tidigare samtal, uppdaterat 2026-11-19. Inget av detta är beställt; varje punkt
väntar på kaptenens (användarens) beslut. Det som redan är byggt står i CLAUDE.md, README.md,
`docs/system/` och `docs/ANDRINGAR.md`; konkreta öppna uppgifter (köra om, prova, utreda) i
`docs/TODO.md`.

## Arkitektur

Grunden håller (sanning/kunskap isär, determinism, `sim/` utan Textual, rapporter som data,
stationer som plugin).

- **Talet renderat i processen.** Talet och effektljuden går genom mixern (`MixPlayer`, `MacSynth`, se
  `docs/system/granssnitt.md`). Fördröjningen uppmätt 2026-11-18: `say -o` tar 0,55–0,75 s per replik
  oavsett längd (mest uppstart och röstladdning); `NSSpeechSynthesizer` i processen med rösten laddad
  20–60 ms (första gången 0,1–0,4 s). Att rendera i processen (pyobjc-Cocoa som beroende på macOS, en
  syntes per röst) skulle ta bort fördröjningen.

## Gränssnitt och grafik

- **Sjögången:** väderprognos i stabens telegram i en kampanj, och sjögången per uppdrag slumpad ur
  årstiden.
- **M4 tjänsteblad** (huvudmenyn): spelade uppdrag med utfall, datum och frö sparade i fil mellan körningar.
- **Fristående app:** om spelet ska delas, paketera fönstret (`fonster.py`) till en fristående app
  (PyInstaller/Briefcase) och signera.

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
- Från radion: stabens svar som styr nästa uppdrag i en kampanj (`Headquarters.received` sparar det vi
  rapporterat), zampolitens samtycke till T-5 (kärnvapenbeslutet).

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

- **Clyde** (`clyde`, skissat 2026-11-18): svår undervattensnavigering, se nedan.

### «Клайд» – in i Firth of Clyde (`clyde`, skissat 2026-11-18)

20 okt 1962: in i Firth of Clyde i undervattensläge förbi Arran och Bute till inloppet av Holy Loch
(amerikanernas Polarisbas), spela in en Polarisubåt som går ut och kom ut oupptäckta före gryningen. Till skillnad från Sundet (foto, farleden) är navigeringen motståndet:
~40 nm från Pladda till Holy Loch och samma väg ut, mest i sund på 1–3 nm med branta stränder.
- **Varför det är svårt:** tidvattnet sätter 1–2 kn i sunden och vänder var 6:e timme; besticket räknar
  inte med strömmen och glider fortare än σ säger (ärligt fel som besättningen ska upptäcka). Varje
  periskopfix kostar (fiskebåtar, färjor, engelsk ubåtsjakt; landmärken bara i dagsljus eller fyrar).
  Bottenfixen är bra (noggrant brittiskt kort, brant botten) men tar 3 min i ≥ 2 kn. 40–150 m djupt:
  djupt gömmer men ger mindre marginal. Molnen i oktober stänger stjärnfixen.
- **Steg** (N1, strömmen ur fixarna, är byggt: `navigation/current.py`, se `docs/system/hav.md`):
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
  Tidvattnet kraftigare än verkligheten (Clyde mest 0,5–1,5 kn, starkast i Kilbrannan Sound)?

### Avhopp till västmakterna (`avhopp`, skissat 2026-11-16, "bra men avvakta")

24 okt 1962, 22:40: kaptenen hoppar av från Kolafjorden till norskt territorialvatten vid Vardø
(4 nm 1962, kontrollera), ~60–70 nm. Medvetet olik Röd Oktober: ingen hemlig drivning, ingen
konspiration, ensam kapten. Tre motståndare:
- **Besättningen:** zampolit och osobist med misstanke (bara sanning) som stiger vid avvikelse från
  ordern och sjunker med tiden: lojal → frågar → misstänker → agerar (osobisten sänder på antenndjup /
  myteri `mutiny`). Spelaren ser tecken; `förklara gyrofel/ubåtsjakt` vars trovärdighet räknas ur
  egna instrument (aldrig slump). Rapportfilterkroken.
- **Staben/Norra flottan:** vet bara vad vi sänt (huvudstaben); missade sambandstillfällen ⇒
  telegram, sedan SKR + Be-6 mot senast kända läge.
- **Väst:** norska patrullbåtar, P-2 från Andøya skuggar. Signalera: undervattenstelefon (≤ 5 nm,
  sovjeter hör), signallampa från bryggan, klartext på nödfrekvens (pejlas). Tidigt eller sent;
  antenndjup ger osobisten chansen.
- Mål `DefectGoal`; utfall mutiny, sänkt, defection_failed, returned. Navigatören är den ende
  invigde och föreslår vägen; övriga föreslår efter ordern.
- Kort variant `avhopp-ut`: 25 nm från Vardø, ett sambandstillfälle missat, SKR 8 nm bakom, 40 min.
- Steg: A1 kust och mål, A2 staben, A3 zampolit och osobist, A4 väst och signalerna, A5 kort variant
  + 8 frön.
- Öppna frågor: kaptenen eller en annan avhoppare; motivet (outsagt, personligt, vägrar T-5).

## Nya system och vyer

System: batytermograf och akustisk prognos, egenbrus, luft (O₂/CO₂, regenereringspatroner), vakter och
trötthet, undervattenstelefon i fler scenarier, torpedomladdning, ljuskulor.

Vyer: eldledning, besättningslista, hydrologi.

## Realismluckor mot Projekt 627A

- Två reaktorer, två turbiner, två axlar.
- Primärkrets och strålningsdos per avdelning.
- Huvudbarlasten bara som regel (ytläge, lodrät djupändring); turbogeneratorer och nöddiesel; hydraulik.
- Syre och regenereringspatroner; vaktschema.
- Tröghets- och radionavigering i Arktis.
- Signalspaning av fiendens ping; sambandsschema och långvåg.
- Minor; nödutrymning.

Historiska anmärkningar: Kuba-ubåtarna 1962 var Projekt 641 (diesel), inte 627A. Provdjup
300 m och krossdjup 450 m är troligen generöst (källor anger ~240/300 m). K-3 nådde Nordpolen
juli 1962. 627A-båtarna låg 1962 i Zapadnaja Litsa; övningen utgår ändå från Poljarnyj
(medvetet val).
