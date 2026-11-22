# K-114 – att göra

Konkreta öppna uppgifter: sådant som behöver köras om, provas, utredas eller beslutas. Idéer som
inte är beställda står i `docs/IDEER.md`. Uppdaterat 2026-11-22. Ta bort det som blir gjort
och för in det i rätt dokument (CLAUDE.md, `docs/system/`, `kalibrering/README.md`).

## Köra om

Inget just nu.

## Prova för hand (riktig terminal, macOS)

Inget just nu (webbversionen provad av kaptenen 2026-11-22: fungerar bra).

## Utreda

Inget just nu.

## Beslut som väntar på kaptenen


Bedömning av ytskotten (`kalibrering/ytskott.py`, siffrorna i `kalibrering/README.md`, 2026-11-21):
mönstret stämmer (ensam rak torped bra till ~2 nm, dålig bortom 3 nm, som historiskt: raka torpeder
sköts på 1 000–3 000 m och i salva). Fire control-felet är rimligt (radar och pejlskiva σ 1°, tio
lägen på tio minuter ger ~0,5 kn fel i farten även på ett stilla mål). Men:
- **Stillaliggande fartyg för högljudda** (`acoustics.source_level`, jagare 137 + 1,25·fart): ett stoppat
  fartyg med bara hjälpmaskiner är troligen 10–15 dB tystare. Passiva målsökare (SET-53, 53-62T efter
  tråden) träffar därför 8 av 8 mot stilla mål, troligen för högt. Ändras det påverkas också sonarns
  hörbarhet för ankrade/stoppade fartyg: kör provspelen och `kontroll.py` efteråt.

## Små brister i bilden

Inget just nu.
