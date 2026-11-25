# K-114 i webbläsaren

Så är webbversionen byggd och publicerad. För att spela behövs bara sidan:
https://thohig.github.io/silent-service-txt/ (se README.md, Spela).

Spelet körs i webbläsaren med [Pyodide](https://pyodide.org) (CPython i WebAssembly) och
[xterm.js](https://xtermjs.org). Det är samma `sim/` och `ui/` som i terminalen; nytt är bara
drivrutinen som ritar och läser tangenter, ljudutgången och talet. Sidan är statisk och ligger på
GitHub Pages: https://thohig.github.io/silent-service-txt/

    uv run python web/bygg.py                  # bygger web/dist
    python3 -m http.server -d web/dist 8000    # prova på http://localhost:8000

`?seed=N` och `?scenario=kuba` i adressen motsvarar `--seed` och `--scenario`.

## Filerna
- `index.html`: laddar xterm.js och Pyodide från jsDelivr, numpy ur Pyodide och Textual
  (fast version, `TEXTUAL`) från PyPI, packar upp `k114.zip` och startar `start.main`.
  Bygger också ljudet (`makeAudio`: en AudioWorklet i 22 050 Hz) och talet (`makeSpeech`:
  `speechSynthesis`) och lämnar dem till Python i bryggan (`bridge.audio`, `bridge.speech`).
- `start.py`: väljer drivrutinen (`TEXTUAL_DRIVER`), lappar Pyodide 0.29:s `WebLoop.create_task`
  (anropar `asyncio.tasks._set_task_name`, som Python 3.13 saknar), kopplar sidans ljud och
  tal (`WebOut.sink`, `ui.ambience.OUTPUT = WebOut`, `WebSpeech.bridge`) och startar `SubApp` med ljudet på.
- `pyodide_driver.py`: Textual-drivrutinen. Skriver till terminalen i sidan, tar tangenter och
  storlek från den på samma händelseslinga (inga trådar). Provas i CPython i `tests/test_webb.py`.
- `web_audio.py`: ljudutgången (`WebOut`, samma gränssnitt som `ui.ambience.AmbientOut`). Fyller var
  50:e ms på en kö 0,25 s fram ur mixern; sidans AudioWorklet (`index.html`, `WORKLET`) spelar kön i
  22 050 Hz, en processor och kö per `WebOut` (`audio.channel()`), så att menyns och spelets ljud blandas
  medan ordern skrivs ut. Ljudklockan står still tills sidan fått en tangent eller ett klick. Mixern kostar ~0,3 ms
  per block om 46 ms i Pyodide, syntesen av bakgrundsljuden 0,2 s och menyns 1 s.
- Talet: `ui.voices.WebSpeech` (vald av `voices.backend()` under Pyodide) läser upp med webbläsarens
  `speechSynthesis` genom sidans `makeSpeech`: Alva och Milena om de finns (Safari och Chrome på Mac
  har dem), annars en annan röst på språket. Utan rysk röst talar besättningen svenska. Talet går inte
  genom mixern, så telefon- och skotteffekten finns inte i webben, och Radio Moskva i menyn är bara brus.
- `bygg.py`: packar `sim/`, `ui/` och startfilerna till `k114.zip` bredvid sidan och ikonerna.
- Ikonerna: `k114.png` (1024 px), flikikonen `k114-32.png` och `apple-touch-icon` `k114-180.png`,
  länkade med storlek i `index.html`. Safari visade ingen ikon när bara den stora fanns. Filerna görs av
  `ikon/bygg.py` (`WEB_SIZES`) och kopieras av `bygg.py` (`ICON_SIZES`). Safari sparar ikoner länge: syns
  ingen efter en ändring, töm `~/Library/Safari/Favicon Cache`.

## Skillnader mot terminalen
- **Inga trådar:** en kort variants uppvärmning körs i bitar (`Game.warm_up_steps`) mellan
  ritningarna i stället för i en tråd (`ui/app.py`, `THREADS`).
- **Ljudet** startar på, som i terminalen (sedan 2026-11-24; hörs först efter en tangent eller ett klick); `ljud` eller
  Inställningar slår av och på (`ctrl+t` tar Chrome själv). Allt utom talet går genom mixern som vanligt (`ui.audio.WebPlayer`); talet är webbläsarens
  (`voices.WebSpeech`), utan telefon- och skotteffekt, och Radio Moskva i menyn är bara brus. Menyns
  syntes görs utan tråd och låser sidan ~1 s när menyn visas med ljudet på.
- **Tangenter:** webbläsaren tar vissa själv (`ctrl+t` och `ctrl+w` i Chrome); `ctrl+q` och menyns
  Avsluta stänger spelet. Sanningsloggen skrivs i minnet och försvinner när sidan laddas om.
- **Fart:** simuleringen går 1–2 gånger långsammare än i CPython (övning ~8 ms per tick mot ~4).
- **Telefoner:** är terminalen mindre än 100×30 tecken, eller har enheten pekskärm utan mus, visar
  sidan en varning innan Pyodide laddas (`mobileWarning` i `index.html`): spelet är för dator, vrid
  telefonen om den står upp, och vyerna nås med ord (`central`, `sjökort`, `sonar` …, `översikt` tillbaka) eftersom
  telefonens tangentbord saknar Tab och Esc. "Spela ändå" startar spelet och sparas i `localStorage`.
- **Första laddningen** hämtar ~15 MB (Pyodide, numpy, Textual); sedan har webbläsaren det i cache.

## Publicering
`.github/workflows/pages.yml` bygger och publicerar vid varje push till main som ändrar `sim/`, `ui/`, `web/` eller
`ikon/` (sedan 2026-11-24; bara dokumentation publicerar inget), och för hand: Actions › pages › Run workflow, eller

    gh workflow run pages.yml --ref main

Två jobb sedan 2026-11-25: `build` packar och laddar upp, `deploy` publicerar. I ett jobb hittade publiceringen
ibland inte paketet som just laddats upp ("Found 0 artifact(s)").

Pages är
påslaget (Source: GitHub Actions, 2026-11-21) och repot offentligt. Besökarna hämtar Pyodide och
xterm.js från jsDelivr och Textual från PyPI; sidan har ingen spårning och sparar inget.
