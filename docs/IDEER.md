# K-114 – idéer och förbättringar som inte är byggda

Samlat 2026-11-15 ur tidigare samtal, genomgånget 2026-11-19. Inget av detta är beställt; varje punkt
väntar på kaptenens (användarens) beslut. Det som redan är byggt står i CLAUDE.md, README.md,
`docs/system/` och `docs/ANDRINGAR.md`; konkreta öppna uppgifter i `docs/TODO.md`; avslagna förslag i
CLAUDE.md.

**Riktlinje (2026-11-19):** ubåtens realism går först, men spelaren ska inte få fler system att sköta.
Realismen ligger hos besättningen: ett nytt system hörs i besättningens rapporter och förslag och märks
när något går fel, ger högst en ny order (helst ingen) och syns i de vyer som finns (inga nya vyer).

## Nya system

Inga just nu (långvågen byggd 2026-11-19, omladdningens slammer 2026-11-19).

## Spelidéer

Ur provskjutningen på säkra lösningar 2026-11-22 (`kalibrering/README.md`):
- **Torpedrummet varnar för målsökande torpeder nära andra fartyg.** `_neutrals_in_lane` hoppar över dem, men
  SET-53 tog ett annat fartyg i 19 av 148 skott (patrullbåten i sundet hörs mer än handelsfartyget).
- **Varning för lång gångtid mot mål som girar.** Benvarningen gäller bara konvojens fartyg; jagare träffades 1
  av 84 gånger med 53-61 eftersom de girar under gången. Torpedrummet kunde säga det och föreslå SET-53 eller
  salva.
- **Anläggningsvinkeln i skjutlösningen**, och en varning för skott rakt för- eller akterifrån där målet är
  smalt (48 % träff mot 60 % från sidan med samma sikte).

## Scenarier

Inga just nu (Clyde byggt 2026-11-19, se `docs/system/scenarier.md`).
