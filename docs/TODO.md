# K-114 – att göra

Konkreta öppna uppgifter: sådant som behöver köras om, provas, utredas eller beslutas. Idéer som
inte är beställda står i `docs/IDEER.md`. Uppdaterat 2026-11-18. Stryk det som är gjort
(`~~…~~` med datum) och flytta det till rätt dokument (CLAUDE.md, `docs/system/`, `kalibrering/README.md`).

## Köra om

- **De särskilda botarna efter slumpen per station** (`Game.rng_for`, 2026-11-18): salva
  (`konvoj_salva.py`, `konvoj.py attack`), grindboten (`sundet_folj.py --följ`, `sundet_in.py`,
  `sundet_ut.py`), sprint och djupt (`jagad_djupt.py`, `jagad_kort.py`), `kuba_jakt.py`, `kuba_flyg.py`,
  `tma_kvalitet.py`, övningens botar (`ovning.py`, `ovning_lyssna.py`, `ovning_torped.py`). Siffrorna i
  `kalibrering/README.md` är från före bytet; passiv och ja-bot är omkörda (`kontroll.py`, inom bruset).
- **Starpom** (`kalibrering/starpom.py`): sömnen håller nu för larm som bara tänder lampan
  (`Station.keeps_time_scale`, 2026-11-18). Ringningar och farlarm per körning bör ha ändrats;
  även utfallen med salva i konvoj och konvoj-kort.
- **Titten före skottet** (2026-11-18) är provkörd, se Utreda. `konvoj_salva.py … titt` (väntar på
  en titt ≤ 60 s, går själv upp på periskopdjup nära målet): konvoj 0 av 8, konvoj-kort 0 av 8, mot
  2 och 0 av 8 för salvaboten. Den kommer sällan till skott (eskortens radar håller oss nere).
- **Inte omkört sedan 2026-11-15:** sundet med sanningsboten (`sundet.py --orakel`), väntläget.

## Prova för hand (riktig terminal, macOS)

- Övningen, periskopet i realtid, ubåtsvyn, hyttvyn (färgerna), sjökortets blyertsmärken.
- Sonarvyn (`sonar`): läsbarheten, relativ bäring under girar, kontaktraderna i små fönster.
- Att ctrl+p inte längre gör något, och att ett klick i loggen lämnar fokus i orderraden.
- Sömnen med starpom: att `sov` håller över en ny kontakt och att telefonen ringer för frågor.

## Utreda

- **Plottets avstånd vid skottet i konvojen** (2026-11-18, `konvoj_salva.py`, felet skrivs vid varje
  skott): lösningar som är god/säker och ≤ 3 nm har avståndsfel på 1–4 nm i nästan alla skott,
  även med en titt ≤ 60 s gammal (konvoj frö 7: säker, fel 2,7 nm). Konvoj-kort frö 1, minut 8:
  S-7 2,9 nm (god, σ 0,65) och 16,8 kn, sanningen 4,7 nm och ~10 kn; senaste titten 9 min gammal.
  Farten överskattas och målet dras in för fort. Det förklarar varför salvorna missar och
  varför titten före skottet inte hjälper. Troligen viktigare än titten.

- **Konvojen med starpom:** ett neutralt fartyg sänkt i en körning med salvaboten (troligen botens
  fel).
- **Sjökortet:** i `jagad-kort`, frö 2 (före slumpbytet), fick bara den ena jagaren märket "först hörd";
  den andra fick troligen sin beteckning på annat sätt än genom sonarens upptäckt.
- **Plottet:** ~9 % grova fel bland goda/säkra lösningar, mest girar de senaste minuterna som
  plottet inte hunnit se (`kalibrering/tma_kvalitet.py`).

## Beslut som väntar på kaptenen

- ~~Konvojen: periskoptitt strax före skjutläget~~ – byggd 2026-11-18 (`off.suggest.fire_look`).
- ~~Sonarvyn: lösningskurvan på som standard~~ – ja, 2026-11-18.
- **Sonarvyn:** ett läge med bara hot? Avgörs efter provningen för hand (tona hellre ned neutrala
  än dölj dem).

## Små brister i bilden

- **Ubåtsvyn:** profilen får 60 % även när den är tom (stor tom yta i 150 kolumner).
- **Hytten:** mitten är tom i stora fönster.
