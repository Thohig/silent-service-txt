# K-114 i webbläsaren

Spelet körs i webbläsaren med [Pyodide](https://pyodide.org) (CPython i WebAssembly) och
[xterm.js](https://xtermjs.org). Det är samma `sim/` och `ui/` som i terminalen; bara drivrutinen
som ritar och läser tangenter är ny. Sidan är statisk och kan ligga på GitHub Pages.

    uv run python web/bygg.py                  # bygger web/dist
    python3 -m http.server -d web/dist 8000    # prova på http://localhost:8000

`?seed=N` och `?scenario=kuba` i adressen motsvarar `--seed` och `--scenario`.

## Filerna
- `index.html`: laddar xterm.js och Pyodide från jsDelivr, numpy ur Pyodide och Textual
  (fast version, `TEXTUAL`) från PyPI, packar upp `k114.zip` och startar `start.main`.
- `start.py`: väljer drivrutinen (`TEXTUAL_DRIVER`), lappar Pyodide 0.29:s `WebLoop.create_task`
  (anropar `asyncio.tasks._set_task_name`, som Python 3.13 saknar) och startar `SubApp` utan ljud.
- `pyodide_driver.py`: Textual-drivrutinen. Skriver till terminalen i sidan, tar tangenter och
  storlek från den på samma händelseslinga (inga trådar). Provas i CPython i `tests/test_webb.py`.
- `bygg.py`: packar `sim/`, `ui/` och startfilerna till `k114.zip` bredvid sidan och ikonen.

## Skillnader mot terminalen
- **Inga trådar:** en kort variants uppvärmning körs i bitar (`Game.warm_up_steps`) mellan
  ritningarna i stället för i en tråd (`ui/app.py`, `THREADS`).
- **Inget ljud:** `say`, `afplay` och `sounddevice` finns inte. Spelet startar tyst och `ljud`
  säger att ljudet saknas.
- **Tangenter:** webbläsaren tar vissa själv (`ctrl+t` och `ctrl+w` i Chrome); `ctrl+q` och menyns
  Avsluta stänger spelet. Sanningsloggen skrivs i minnet och försvinner när sidan laddas om.
- **Fart:** simuleringen går 1–2 gånger långsammare än i CPython (övning ~8 ms per tick mot ~4).
- **Första laddningen** hämtar ~15 MB (Pyodide, numpy, Textual); sedan har webbläsaren det i cache.

## Publicering
`.github/workflows/pages.yml` bygger och publicerar vid push till main som rör `sim/`, `ui/` eller
`web/`. En gång i repots inställningar: Settings › Pages › Source: GitHub Actions.
