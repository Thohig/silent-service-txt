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

| Order | Betydelse |
|---|---|
| `kurs 090` | ny kurs (000–359) |
| `fart 5` / `stopp` | fart i knop |
| `djup 100` | djup i meter |
| `tid 1` `tid 2` `tid 5` `tid 10` | tidskomprimering (faller till 1× vid larm) |
| `läge S-1` | plottlagets lösning: kurs, fart, avstånd och kvalitet |
| `plot S-1` | loggade bäringar mot aktuell lösning |
| `hjälp` | orderlista |

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
  stations/          ett system ombord per modul
    base.py          Station: COMMANDS, on_order, update, say
    navigation.py    kurs, fart, djup
    sonar_room.py    sonaroperatören
    plot.py          plottlaget
ui/                  Textual
```

### Lägga till ett system

1. Skapa `sim/stations/<system>.py` med en klass som ärver `Station`.
2. Definiera ordertyper (`Order`-dataklasser) och `COMMANDS` med
   `CommandSpec(mönster, bygg, hjälptext)`.
3. Hantera dina order i `on_order` och kör löpande logik i `update`.
4. Rapportera med `self.say("system.händelse", {...data...})` och lägg till
   en fras i `phrases.PHRASES`.
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
