# K-114 – att göra

Konkreta öppna uppgifter: sådant som behöver köras om, provas, utredas eller beslutas. Idéer som
inte är beställda står i `docs/IDEER.md`. Uppdaterat 2026-11-21. Ta bort det som blir gjort
och för in det i rätt dokument (CLAUDE.md, `docs/system/`, `kalibrering/README.md`).

## Köra om

Inget just nu.

## Prova för hand (riktig terminal, macOS)

- **Webbversionen** i Safari och Chrome på Mac (`web/README.md`): tangenter (Tab, Esc, ctrl-tangenter),
  typsnittet (lådtecken och punktgrafik i centralen), storleksändring och ett helt uppdrag.

## Utreda

- **konvoj-kort, ja-boten:** efter rättelserna från provspelet (2026-11-21) slutar den med en skjuten men
  missad salva i 3 av 8 frön i stället för 1 (tiden ute 7 ⇒ 5). Ingen av rättelserna rör anfallet direkt;
  troligen skiftar sprinten eller glesare skenmål vad ja-boten hinner med. Se om fröna sköt på sämre lösningar.

## Beslut som väntar på kaptenen


- **Ljud i webbversionen:** talet med webbläsarens talsyntes (`speechSynthesis`; rysk röst beror på
  webbläsare och system) och ljuden och mixern med Web Audio, kopplat in i `voices.backend()` och
  `ambience`. Ett eget större steg; webben är tyst tills dess.

Bedömning av ytskotten (`kalibrering/ytskott.py`, siffrorna i `kalibrering/README.md`, 2026-11-21):
mönstret stämmer (ensam rak torped bra till ~2 nm, dålig bortom 3 nm, som historiskt: raka torpeder
sköts på 1 000–3 000 m och i salva). Fire control-felet är rimligt (radar och pejlskiva σ 1°, tio
lägen på tio minuter ger ~0,5 kn fel i farten även på ett stilla mål). Men:
- **Stillaliggande fartyg för högljudda** (`acoustics.source_level`, jagare 137 + 1,25·fart): ett stoppat
  fartyg med bara hjälpmaskiner är troligen 10–15 dB tystare. Passiva målsökare (SET-53, 53-62T efter
  tråden) träffar därför 8 av 8 mot stilla mål, troligen för högt. Ändras det påverkas också sonarns
  hörbarhet för ankrade/stoppade fartyg: kör provspelen och `kontroll.py` efteråt.
- **Raka torpeder går helt rakt** (`weapons.py`): ingen spridning från gyrot (σ ~0,3–0,5°), inga fel- eller
  förtidsdetonationer. Gör dem något för träffsäkra på långt håll.
- **Träffytan är en cirkel** (`HIT_RADIUS_NM` 0,03 nm, `HULL_HALF_NM`) oavsett vinkel mot målet; mot för
  eller akter är en jagare ~12 m bred. En ellips efter längd och bredd vore riktigare, och strängare.
- **Provskjutningen bör köras med olika frön per avstånd och 20–30 frön.** Nu ger samma frö troligen samma
  sensorslump på alla avstånd (samma två frön träffade överallt), så 48 skott är i praktiken 8 försök
  (2 av 8 ≈ 5–55 %).

## Små brister i bilden

Inget just nu.
