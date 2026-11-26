# K-114 – att göra

Konkreta öppna uppgifter: sådant som behöver köras om, provas, utredas eller beslutas. Idéer som
inte är beställda står i `docs/IDEER.md`. Uppdaterat 2026-11-26. Ta bort det som blir gjort
och för in det i rätt dokument (CLAUDE.md, `docs/system/`, `kalibrering/README.md`).

## Köra om

Inget just nu.

## Prova för hand (riktig terminal, macOS)

Webbversionen provad av kaptenen 2026-11-22: fungerar bra. Byggt 2026-11-24 och bara provat huvudlöst
(`run_test`, skärmbilder):
- Loggboken som lager (2026-11-25): PageUp/PageDown/Esc i Terminal på macOS och i webbläsaren (bläddrar sidan i
  stället, eller når tangenten spelet?). Räcker loggremsan med 7 rader under översikten i 80 × 24?
- Utsikten (2026-11-25): bryggans panorama, ↓ kikarens okular och ↑ tillbaka i ytläge; periskopbilden under ytan.
- Bandet i Clyde (2026-11-26): "kurs … för att skära av den" och "vi hinner inte ikapp"; känns det rätt, och borde
  sonar då föreslå något (vänta vid farleden)?
- Torpedlarmet (2026-11-26): en torped som tystnar tidigt håller larmet i upp till 12 min ("håll farten"); blir det
  för länge i 28 knop när den faktiskt är borta?
- Radion i kuba-kort och konvoj-kort (2026-11-25): "väntar på djupet" på en jagare med dålig lösning, och
  `radio.closing` 5 min före stängning; för försiktig, eller lagom?
- Huvudskärmen: översikten med loggremsan (9 rader) i ett vanligt terminalfönster och i webbläsaren. Räcker
  remsan för att följa rapporterna, eller behövs fler rader? Är sjökortet i översikten lagom inzoomat?
- Centralen i helskärm (`central`, Tab): instrumenten och lutningsmätaren i fart, snabbtelefonens lampor när
  stationerna talar.
- Talnivån med Milena: blir `tal viktigt` lagom, saknas något som borde höras (ändra `ROUTINE_TYPES` i
  `ui/audio.py`), och låter "Есть" som kvittens rätt? Mät före och efter med `kalibrering/talniva.py --typer`
  (i jagad-kort läses sonarens "pingarna mycket starka" och maskins slammer mest på nivån viktigt).
- Stampvinkeln i spel: lutningen vid djupbyte, "Brant vinkel" och slammer under jakt.
- Skadekontrollen (2026-11-25, bara huvudlöst): läckor, länsning i tystnad, `reparera`, fastnat djuproder och
  det sänkta provdjupet under en riktig sjunkbombning (jagad, krig). Blir det för mycket larm i följd?
- Genomskärningen med vatten i avdelningarna och de gula skotten, centralen som text i 80 × 24.
- Ljudet ombord: läckan, droppet, pumparna, reparationens slag och den tysta filningen; lagom starka i mixern
  och i webbläsaren?
- Livet i världen: regn (sonars smatter), dimma (periskopet, bryggan, mistlurarna), vraket (fix med ekolodet,
  gömma sig bredvid), trålen (`trawl.caught`), helikoptern (`sonar.dip`), B-36 i kuba. Kollisionen på
  periskopdjup och jagarens ramning.

## Utreda

Inget just nu.

## Beslut som väntar på kaptenen

- Helikopterns Mk 44 (`HeloDef.torpedo`) är av: med den förlorade ja-boten 6 av 8 i krig. Ska den på med en
  mildare regel (t.ex. två eko i rad, eller bara i krig-kort)?
- Snorkel: K-114 har ingen i spelet. Hade den riktiga 627A en (för dieselgeneratorerna)? I så fall kan det bli
  ett system (batteriet laddas på snorkeldjup när reaktorn står; hörs och syns), en order.

## Små brister i bilden

Inget just nu.
