# K-114 – idéer och förbättringar som inte är byggda

Samlat 2026-11-15 ur tidigare samtal, genomgånget 2026-11-19. Inget av detta är beställt; varje punkt
väntar på kaptenens (användarens) beslut. Det som redan är byggt står i CLAUDE.md, README.md,
`docs/system/` och `docs/ANDRINGAR.md`; konkreta öppna uppgifter i `docs/TODO.md`; avslagna förslag i
CLAUDE.md.

**Riktlinje (2026-11-19):** ubåtens realism går först, men spelaren ska inte få fler system att sköta.
Realismen ligger hos besättningen: ett nytt system hörs i besättningens rapporter och förslag och märks
när något går fel, ger högst en ny order (helst ingen) och syns i de vyer som finns (inga nya vyer).

## Nya system

- **Döda sektorn akterut i alla scenarier** (2026-11-23, användarens önskan att anteckna): sonarns döda sektor
  (`OwnShip.baffle_deg`, `sim/sonar.py` `baffle_loss`, sonars gir för att lyssna i `sim/stations/baffles.py`) finns
  bara i Svansen. Realistiskt gäller den alltid: en jagare akterut hörs sämre när vi går fort, och sonar vill lyssna
  akterut efter långa raka sträckor. Kräver omkalibrering av alla scenarier (`kalibrering/kontroll.py`, ny
  baslinje) och en titt på jaktens förslag (undanmanövern bort från jagaren lägger den i sektorn).

## Spelidéer

Inga just nu (provskjutningens tre idéer byggda 2026-11-22).

## Scenarier

Inga just nu (Clyde byggt 2026-11-19, se `docs/system/scenarier.md`).
