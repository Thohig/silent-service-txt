# K-114 – att göra

Konkreta öppna uppgifter: sådant som behöver köras om, provas, utredas eller beslutas. Idéer som
inte är beställda står i `docs/IDEER.md`. Uppdaterat 2026-11-23. Ta bort det som blir gjort
och för in det i rätt dokument (CLAUDE.md, `docs/system/`, `kalibrering/README.md`).

## Köra om

Inget just nu.

## Prova för hand (riktig terminal, macOS)

Inget just nu (webbversionen provad av kaptenen 2026-11-22: fungerar bra).

## Utreda

Från skyttebotens körning 2026-11-23 (22 scenarier × 8 frön):
- **Säkra lösningar som är grovt fel.** kuba-kort 5: plottet gick på 90 s från god (6,2 nm) till säker (4,4 nm);
  sanningen 6,3 nm, kursen 148° fel. krig 2: jagaren S-6 säker på 1,2 nm, sanningen 3,5 nm, 2,5 min efter att
  den hörts igen efter 7 min tappad. Idé: en lösning som flyttat sig mer än 2σ från den förra blir inte säker,
  och en lucka på flera minuter i bäringarna börjar om lösningen.
- **Målsökaren tar en neutral bortom målet.** konvoj-kort 1: SET-53 mot jagaren S-4, jagaren girade och
  torpeden tog det civila S-2 utan varning. `_seeker_rivals` ser bara 0,6 nm kring träffpunkten, men
  målsökaren söker i ±35° hela vägen.
- **Varning för en annan neutral räknas som bekräftelse av målet** (`_neutrals_clear` sätter `_confirmed`): ett
  handelsfartyg kan skjutas utan att torpedrummet säger att målet självt är civilt.
- **Långa skott mot mål som girar.** 0 träffar på 26 mot jagare, transporter och tankfartyg på 4–8 nm;
  torpedrummet kunde varna för gångtiden mot jagande och sicksackande mål tydligare.
- Småsaker: navigatören kvitterar ett djup som redan gäller när det ingår i ett sammansatt förslag;
  `torp.ready` föreslår nytt skott medan en torped går mot samma mål; sonar tappar och klassar 5–6 kontakter
  i samma sekund på var sin rad.

## Beslut som väntar på kaptenen

Inget just nu.

## Små brister i bilden

Inget just nu.
