# K-114 – att göra

Konkreta öppna uppgifter: sådant som behöver köras om, provas, utredas eller beslutas. Idéer som
inte är beställda står i `docs/IDEER.md`. Uppdaterat 2026-11-22. Ta bort det som blir gjort
och för in det i rätt dokument (CLAUDE.md, `docs/system/`, `kalibrering/README.md`).

## Köra om

Inget just nu.

## Prova för hand (riktig terminal, macOS)

Inget just nu (webbversionen provad av kaptenen 2026-11-22: fungerar bra).

## Utreda

- Radion räknar varje detonation av en egen torped som "TORPEDTRÄFF HÖRD" i rapporten (`radio/station.py`,
  `_hit_t` på `OwnTorpedoHeard` "detonated"), också en förtidsdetonation eller en torped på grund. Borde följa
  torpedrummets bedömning (`torp.run.early`) eller brytningsljudet. (Provskjutningen 2026-11-22.)
- Plottets kurs är för säker: i provskjutningen 2026-11-22 låg kursfelet utanför 3σ i 18 % av de säkra
  lösningarna på mål > 3 kn (läget 7 %). `kalibrering/tma_kvalitet.py` och `skott_saker.py`.

## Beslut som väntar på kaptenen

Inget just nu.

## Små brister i bilden

Inget just nu.
