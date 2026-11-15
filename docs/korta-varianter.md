# Korta varianter – plan

Mål: varje scenario ska kunna spelas i en kort variant (15–25 min speltid) som börjar mitt i
läget, med första kontakt eller beslut inom 2–3 minuter. De långa varianterna finns kvar.

Flytta en variant från **Kvar** till **Klart** när den är byggd, testad och kalibrerad. När allt
är klart tas filen bort; CLAUDE.md beskriver då resultatet.

## Klart

- **Mekanismen** (se CLAUDE.md, "Korta varianter"):
  - `Scenario.warmup = Warmup(seconds, pilot)`: `Game` kör vakten före kaptenen med en fast
    plan; `pilot(game, t)` ger order via `game.command`. Kunskapen byggs av sensorerna.
  - Gränssnittet skapar `Game(..., warm_up=False)` och kör `game.warm_up()` i en tråd medan
    ordern skrivs ut. Det prenumererar först efteråt, så vaktens rapporter syns inte.
  - `Handover` ⇒ vakthavande säger `off.briefing` (konvoj, kontakter, besticket).
  - Loggboken börjar vid överlämnandet.
  - Tidsgränsen är `World.patrol_end` = uppvärmning + speltid, med scenariots
    `outcome_text["patrol_end"]`.
  - `ScenarioDef.minutes` visas i väljaren.
  - En kort variant är en egen nyckel som bygger på det långa scenariot.
  - Tester: `tests/test_warmup.py`.
- **`konvoj-kort`, "Skjutläge":** konvojen 13–15 nm bort, vakt i 35 min (periskopdjup, fart 3,
  svep var 4:e min), sedan 45 min. Kalibrering står i CLAUDE.md.

## Kvar, i byggordning

### Steg 3 – utan (eller med mycket kort) uppvärmning

**`jagad-kort`, "Skarpt", ~15 min**
- **Start:** som `hunted_scenario`, men skarpa bomber från start (`roe="lethal"` eller
  `escalate_after=0`) och DD1 1,5 nm bort i anfallsgång. Sonaren hör snabb pingtakt direkt.
- **Kvadraten:** mindre, så att det tar ~15 min att komma ut djupt och fort.
- **Mål:** samma `escape` som Jagade.
- **Tidsgräns:** ~25 min.
- **Nytt i koden:** troligen bara parametrar till `hunted_scenario` (storlek, avstånd, roe).

**`konvoj-mot`, "Motanfallet", ~15 min**
- **Start:** salvan har just gått mot ett konvojfartyg och en torped träffar efter 30–60 s.
  En eskort girar mot oss från 1,5 nm med skarpa bomber.
- **Mål:** att bryta kontakten. Variant av `strike` eller `escape`: ingen jägare har oss
  10 min efter sänkningen.
- **Uppvärmning:** kort. Pilot som avfyrar salvan från ett skjutläge, så att torpedrummet och
  sonaren känner till torpederna. Lägg inte in torpeder direkt i världen.
- **Nytt i koden:** konvojen placerad i skjutläge vid start, plus pilot som skjuter (salvan
  måste upprepas, eftersom torpedrummet vill ha bekräftelse när målet inte är säkert klassat).

### Steg 4 – uppvärmning med fast plan

**`kuba-kort`, "Sambandsfönstret", ~20 min**
- **Start:** jagaren 3–4 nm bort i patrull med övningsbomber.
  Flyget efter 5–10 min (`KUBA_AIR` med kortare första väntan).
- **Uppvärmning:** ~15 min, så att sonar och plott har jagaren.
- **Radiofönstret:** öppnar några minuter efter överlämnandet och är öppet i 15 min.
- **Mål:** rapporten sänd och ingen jägare med datum på oss när fönstret stänger.
- **Nytt i koden:** målet i `World._check_outcome` (t.ex. `mission["report"]`).

**`sundet-in`, "Grinden", ~20 min**
- **Start:** i väntläget, med ett inkommande fartyg 1,5 nm från grinden.
- **Uppvärmning:** ~10 min, så att sonar och plott har fartyget.
- **Mål:** ett foto av god kvalitet. Utvägen ingår inte.
- **Nytt i koden:** mål som slutar vid fotot (i dag kräver `escape` foto *och* utväg).

**`sundet-ut`, "Ut med filmen", ~20 min**
- **Start:** innanför nätet med filmen och patrullbåten i rörelse. Ett utgående fartyg
  lämnar kajen om 5 min.
- **Mål:** ute ur området (`escape` som i dag).
- **Svårt:** en uppvärmning genom hela inträngningen är för opålitlig. Bygg startläget direkt
  (ubåten innanför nätet) och för in fotot som en händelse (`PhotoTaken`) under en kort
  uppvärmning, så att `Knowledge.best_photo` byggs via bussen.

### Steg 5

**`arktis-kort`, "Sista milen", ~25 min**
- **Start:** 2,5–3,5 nm från Nord-7.
- **Uppvärmning:** ~20 min på kurs mot stationen med isekolod, så att iskartan har öppningar
  bakom oss.
- **Den amerikanska ubåten:** hörd, 3–4 nm bort, på väg mot samma plats.
- **Branden:** efter 5–12 min (`mission["fire_at"]`).
- **Mål och tidsgräns:** samma mål som i dag (ytläge inom 1,5 nm), tidsgräns ~30 min.

## Arbetssätt för varje variant

- Bygg en variant i taget och committa efter varje.
- **Provkörning:** 8 frön med den passiva boten, ja-boten (inga vapen) och boten med
  besättningens verktyg. Skript i scratchpad, inte i repot.
- **Riktmärken:**
  - första förslag eller kontakt inom 3 min;
  - ja-boten klarar ~2–4 av 8;
  - de viktiga lösningarna har minst kvaliteten osäker vid överlämnandet.
- **Siffrorna** förs in under Kalibrering i CLAUDE.md.
- **Tester i `tests/`:** varianten startar med kontakt, och tidsgränsen ger rätt utfall.
  Statistiska påståenden testas över flera frön, men så få som möjligt, eftersom
  uppvärmningen tar ~5–8 s per frö.
- **README:** lägg till varianten i scenariotabellen och i `--scenario`-raden.

## Öppna frågor

- **Testsviten:** tar flera minuter, inte ~3 s som CLAUDE.md säger. Antingen uppdateras
  siffran eller så görs de långsamma testerna snabbare (t.ex. färre frön, eller markera dem).
- **Konvojens träffsiffra:** en bot som skjuter `salva` (upprepad) mot klassad
  transport/tanker inom 3 nm med lösning minst osäker sänker 1 av 8, både i `konvoj` och
  `konvoj-kort`. CLAUDE.md anger 3 av 8 för konvojboten (`convoy_bots.py`, som inte finns
  kvar). Reda ut om skillnaden ligger i boten eller i spelet.
