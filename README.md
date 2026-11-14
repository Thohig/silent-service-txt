# K-114 – textbaserad ubåtssimulator, 1962

Du är kapten på en sovjetisk atomubåt. Du ger skrivna order och besättningen
rapporterar. Fienden syns aldrig direkt, bara genom sonaroperatörens bäringar
och plottlagets målrörelseanalys.

## Köra

```bash
uv run main.py            # nytt slumpat scenario
uv run main.py --seed 4   # reproducerbart scenario
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
| Navigation | `position` · `fix` (periskopdjup) · `ekolod` |
| Maskin | `smygmotor` · `turbin` · `stäng reaktorn` · `starta reaktorn` · `nödblåsning` · `maskin` |
| Vakthavande | `periskop` · `radar` (periskopdjup; radarvarnaren är automatisk) |
| Radio | `sänd rapport` (periskopdjup, kan pejlas) · `radio` |
| Torped | `tuber` · `torpeder` · `skjutlösning S-1` · `eld tub 1 mot S-1` · `eld tub 1 kurs 045` · `ladda tub 7 SET-53` · `skenmål` |
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
| Språngskikt (60 m) | Skyddar mot jagarens sonar, men vi hör också sämre genom det. |
| Roder, barlast, skrov | Djupändring kräver fart. Under provdjup (300 m) knakar skrovet; 450 m krossar det. |
| Skador, läckor, nödblåsning | Sjunkbomber ger skador och vatteninträngning; reparationer tar tid. |
| Passiv och aktiv sonar | Passiv ger bäringar; aktiv ger avstånd men avslöjar oss. |
| Periskop, radar, radarvarnare | Avstånd och kurs på periskopdjup, med risk att synas. |
| Navigering | Besticket driver med ström och loggfel; fix kräver periskopet. |
| Radio | Sambandstillfällen kl 05:00, 06:30 och 08:00 på antenndjup. Sändning pejlas. |
| Torpeder | 53-61 (rak, snabb), SET-53 (målsökande), T-5 (kärnladdning, spärrad utan order). |
| Torpeder i vattnet | Sonar följer egna torpeder. Torpedrummet rapporterar normal gång, sväng (målsökning), tappad torped, detonation och miss. `torpeder` ger gångtid, tid till beräknad träff, räckvidd kvar och senaste bäring. |
| Skenmål | Drar jagarens sonar bort från ubåten. |

Jagaren pingar, söker kring sin bild av var vi är och fäller
signalsjunkbomber för att tvinga upp oss. Om vi skjuter blir sjunkbomberna
skarpa.

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
  environment.py     språngskikt, ström, dygnsljus
  entities.py        fartyg, transienter, emissioner
  ownship.py         egen ubåt: reaktor, batteri, skrov, skador
  enemy.py           jagarens sensorer och beteende
  weapons.py         torpeder, sjunkbomber, skenmål
  firecontrol.py     skjutlösning (ren matematik på kunskap)
  stations/          ett system ombord per modul
    base.py          Station: COMMANDS, on_order, update, say, suggest
    navigation.py    kurs, fart, djup, bestick, fix, ekolod
    engineering.py   maskin och skadekontroll
    sonar_room.py    sonar, transienter, aktiv sonar
    officer.py       periskop, radar, radarvarnare
    radio.py         sambandstillfällen och rapporter
    plot.py          plottlaget
    torpedo_room.py  torpedrum och eldledning
ui/                  Textual
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
