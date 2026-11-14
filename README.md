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

- `sim/` är ren Python utan Textual. Den skiljer **sanning** (`world.py`) från
  **kunskap** (`knowledge.py`). Bara sonaroperatören (`sonar.py`) läser
  sanningen, och han lämnar bara ifrån sig brusiga bäringar.
- `sim/events.py` är händelsebussen mellan simulering, besättning och
  gränssnitt. Framtida talsyntes och berättelselager kopplas in här.
- `sim/reports.py` har en `ReportQueue` med rapportfilter, som är kroken för
  trötthet, moral, lojalitet och sabotage.
- `sim/crew.py` låter all påverkan på skicklighet gå via
  `CrewMember.effective_skill()`.
- `sim/tma.py` gör bäringsbaserad minsta-kvadratanalys. Kvaliteten
  (dålig/osäker/god/säker) härleds ur lösningens kovarians.
- `ui/` innehåller Textual-gränssnittet.
