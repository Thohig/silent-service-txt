# K-114 – idéer och förbättringar som inte är byggda

Samlat 2026-11-15 ur tidigare samtal, genomgånget 2026-11-19. Inget av detta är beställt; varje punkt
väntar på kaptenens (användarens) beslut. Det som redan är byggt står i CLAUDE.md, README.md,
`docs/system/` och `docs/ANDRINGAR.md`; konkreta öppna uppgifter i `docs/TODO.md`; avslagna förslag i
CLAUDE.md.

**Riktlinje (2026-11-19):** ubåtens realism går först, men spelaren ska inte få fler system att sköta.
Realismen ligger hos besättningen: ett nytt system hörs i besättningens rapporter och förslag och märks
när något går fel, ger högst en ny order (helst ingen) och syns i de vyer som finns (inga nya vyer).

## Nya system

Inga just nu (långvågen byggd 2026-11-19).

Bara med det som behöver dem:
- **Luften** (syre, koldioxid, regenereringspatroner): slås ihop med koldioxiden som finns, i maskins
  rapporter och på systemtavlan; betydelse först om något kräver det.
- **Omladdningen hörs:** omladdningen tar redan 5 minuter; det som saknas är att den slamrar (en transient
  jagaren kan höra).

## Spelidéer

- **Jagarkaptener med personlighet** (variation i fiendens beteende).
- **Viskningar och skrovknak under jakt;** **"torped i vattnet"-nedräkning** (besättningen räknar).
- **Starpom respekterar telefonorder** (2026-11-19): i dag kan ett nytt förslag inom mandatet ersätta en
  order kaptenen gett per telefon (`on_suggestion` har ingen sådan invändning). Förslag: ett förslag som
  går emot en telefonorder från de senaste 10 minuterna avgör han inte själv utan ringer ("Sonar föreslår
  djup 150, ni beordrade 50"); larm och jakt undantagna.

## Scenarier

- **Clyde** (`clyde`, skissat 2026-11-18): svår undervattensnavigering med de system som finns, se nedan.

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
  N5 motstånd och mål: engelska patrullbåtar, hydrofonlinje vid Cumbrae, en minerad sträcka i ett
  sund, fiskebåtar, färjan Wemyss Bay–Rothesay; `RecordGoal` (Polarisubåten hörd länge nog med god kvalitet), sedan `EscapeGoal`
  före gryningen och `GroundingFails`.
  N6 kort variant `clyde-in`: söder om Little Cumbrae, bestick σ 0,8 nm, strömmen på väg att vända,
  ~40 min; 8 frön enligt riktmärkena.
- **Spelkänslan:** titt (fix och risk), bottenfix (tid och fart) eller lita på besticket (σ växer,
  strömmen okänd). Besättningen säger hur säkert läget är ("läget osäkert, 0,6 nm, sundet är 1,4
  brett"); navigatören föreslår vad som behövs, `_shoal_watch` varnar.
- **Öppna frågor:** Holy Loch eller en påhittad bas (en påhittad norsk fjord vore mindre arbete i N4)?
  Tidvattnet kraftigare än verkligheten (Clyde mest 0,5–1,5 kn, starkast i Kilbrannan Sound)?

## Gränssnitt

- **M4 tjänsteblad** (huvudmenyn): spelade uppdrag med utfall, datum och frö sparade i fil mellan körningar.

## Historiska anmärkningar

Kuba-ubåtarna 1962 var Projekt 641 (diesel), inte 627A. Provdjup 300 m och krossdjup 450 m är troligen
generöst (källor anger ~240/300 m). K-3 nådde Nordpolen juli 1962. 627A-båtarna låg 1962 i Zapadnaja
Litsa; övningen utgår ändå från Poljarnyj (medvetet val). På B-59 krävdes tre nycklar för att
flottiljens stabschef (Archipov) var ombord; på de andra båtarna räckte kapten och zampolit.
