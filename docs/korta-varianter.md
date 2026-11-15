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
- **`konvoj-mot`, "Motanfallet":** vakten skjuter salvan inom 2–4 min, kaptenen tar över ~45 s före
  träff med en eskort i anfall. Kalibrering står i CLAUDE.md.
- **`jagad-kort`, "Skarpt":** utan uppvärmning, kvadraten 7 nm, båda jagarna skarpa från start,
  DD2 spärrar den korta vägen ut. Tidsgräns 30 min. Kalibrering står i CLAUDE.md.

## Kvar, i byggordning

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
- **Konvojens träffsiffra:** delvis utrett. Plottet använde inte periskopets kurs och fart och
  märkte inte girar mellan tittarna, så lösningar kallades säkra med 1 nm och 100° fel. Rättat (se
  TMA under Kalibrering). Konvojboten (ja + salva mot klassad transport/tanker ≤ 3 nm, lösning
  ≥ osäker): `konvoj` 2 av 8 (förut 1), `konvoj-kort` fortfarande 1 av 8. Boten skjuter på gamla
  lösningar (tittar var 4:e min, ben på 5–10 min); en bot som skjuter strax efter en titt träffar
  oftare (vakten i `konvoj-mot`: 6 av 6 salvor träffade).
- **Långa Jagade har glidit:** med samma botar som för `jagad-kort` (12 000 s) ger `jagad` i dag
  ja-boten 1 av 8 och djupt och fort 1 av 8 (oftast sänkta, `lost`), mot 3 och 7 i CLAUDE.md.
  Samma resultat före och efter `jagad-kort`, så det har kommit med någon tidigare ändring.
