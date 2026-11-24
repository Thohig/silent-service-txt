# K-114 – att göra

Konkreta öppna uppgifter: sådant som behöver köras om, provas, utredas eller beslutas. Idéer som
inte är beställda står i `docs/IDEER.md`. Uppdaterat 2026-11-24. Ta bort det som blir gjort
och för in det i rätt dokument (CLAUDE.md, `docs/system/`, `kalibrering/README.md`).

## Köra om

Inget just nu.

## Prova för hand (riktig terminal, macOS)

Inget just nu (webbversionen provad av kaptenen 2026-11-22: fungerar bra).

## Utreda

- **Krig-kort fullföljer färre patruller** (kontrollen 2026-11-24, ja-boten, 32 frön): 3c9ce48 10 av 32
  `patrol_done`, d3d4621 5, arbetskopian 6. Inte konvojgrupperingen (lika med och utan) och inte flygpausen
  `AIR_HOLD_S` (5 utan). Kvar att pröva en i taget: `_fire_depth_watch`, `PING_MIN_GAP_S`, `Game._drop_vetoed`,
  maskins sprintfart, bottenfixens fartgräns. Sedan kontrollen för alla, `--slow` och `kontroll.py --spara`.
- **Vaken under isen glider förbi** (arktis frö 21, skytt 2026-11-24): "stoppa här" i 5 kn när isekolodet ser
  nyis ovanför, vi glider ~120 m förbi, vänder och missar eller står med tjock is för och akter. Fyra försök på
  16 min, och sambandstillfället missades. Back i maskin provades (40 m i stället för 120 m) och blev sämre: vi
  stannade i kanten där ekolodet först såg råken, glidet tog oss förut närmare mitten (arktis ja: förlorade
  1 ⇒ 4 av 8, stationen nådd 5 ⇒ 3). Det som behövs är troligen att stanna mitt i råken: sakta in över den
  och vända tillbaka till mitten när ekolodet ser dess slut.

## Beslut som väntar på kaptenen

Inget just nu.

## Små brister i bilden

Inget just nu.
