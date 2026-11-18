# K-114 – att göra

Konkreta öppna uppgifter: sådant som behöver köras om, provas, utredas eller beslutas. Idéer som
inte är beställda står i `docs/IDEER.md`. Uppdaterat 2026-11-18. Stryk det som är gjort
(`~~…~~` med datum) och flytta det till rätt dokument (CLAUDE.md, `docs/system/`, `kalibrering/README.md`).

## Köra om

- ~~De särskilda botarna, starpom och sundet med sanningsboten~~ – omkörda 2026-11-18, se tabellen under
  Siffrorna i `kalibrering/README.md`. Inget har blivit märkbart sämre; `kontroll.py` (passiv och ja-bot
  mot baslinjen) är inte omkörd efter processbruset för sicksack.

## Prova för hand (riktig terminal, macOS)

- Övningen, periskopet i realtid, ubåtsvyn, hyttvyn (färgerna), sjökortets blyertsmärken.
- Sonarvyn (`sonar`): läsbarheten, relativ bäring under girar, kontaktraderna i små fönster.
- Att ctrl+p inte längre gör något, och att ett klick i loggen lämnar fokus i orderraden.
- Sömnen med starpom: att `sov` håller över en ny kontakt och att telefonen ringer för frågor.

## Utreda

- ~~Plottets avstånd vid skottet i konvojen~~ – 2026-11-18: sicksackande mål fick för litet
  processbrus (q = 1) och lösningen blev för säker; nu q = 30 för konvojfartyg och mål med två girar
  (`Knowledge.zigzags`). Grova fel bland goda/säkra i konvoj-kort 6,5 % ⇒ 3,1 %, > 3σ 12 % ⇒ 4 %.
- ~~Konvojen med starpom: ett neutralt fartyg sänkt~~ – 2026-11-18, konvoj-kort frö 4: rätt mål, men
  plottet sa 2,0 nm i stället för 4,0; salvans raka torpeder gick vidare och träffade handelsfartyget S-3,
  som sonar hade. Både botens och spelets fel: se beslutet nedan.
- ~~Sjökortet: bara den ena jagaren fick "först hörd"~~ – 2026-11-18: båda fick märket, men en etikett
  som krockade (t.ex. med ett nyare pingmärke) ritades inte alls; nu flyttas den en rad.
- **Plottet:** grova fel bland goda/säkra 6,9 % ⇒ 4,8 % (2026-11-18, `tma_kvalitet.py`). Kvar:
  sundet (få lösningar, säker grovt 18 %) och girar de senaste minuterna.

## Beslut som väntar på kaptenen

- **Torpedrummet:** varna (eller vägra utan `ändå`) när en känd neutral kontakt ligger nära
  skjutriktningen inom torpedens räckvidd? Ur kunskapen: bäring och lösning på neutrala.

- ~~Konvojen: periskoptitt strax före skjutläget~~ – byggd 2026-11-18 (`off.suggest.fire_look`).
- ~~Sonarvyn: lösningskurvan på som standard~~ – ja, 2026-11-18.
- **Sonarvyn:** ett läge med bara hot? Avgörs efter provningen för hand (tona hellre ned neutrala
  än dölj dem).

## Små brister i bilden

- **Ubåtsvyn:** profilen får 60 % även när den är tom (stor tom yta i 150 kolumner).
- **Hytten:** mitten är tom i stora fönster.
