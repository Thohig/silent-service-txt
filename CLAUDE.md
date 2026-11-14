# K-114 – arbetsregler för Claude

Textbaserad ubåtssimulator i realtid: sovjetisk atomubåt (Projekt 627A-liknande),
oktober 1962. Python 3.12, Textual, numpy, uv. Användaren kör macOS (Apple Silicon).
Översikt, order och system finns i README.md – läs den först.

## Språk
- Svara användaren på svenska.
- Allt spelaren ser är svenska: fraser, order, rapporter. Kod, identifierare och
  kommentarer får vara svenska eller engelska, men följ omgivande fil.
- Decimaltal i spelet med komma (`fmt.nm`, `fmt.kn`), kurser tresiffriga (`fmt_course`).

## Kommandon
```bash
uv run main.py [--seed N]     # spela
uv run pytest -q              # alla tester (~3 s), ska alltid vara gröna
```

## Designprinciper (får inte brytas)
1. **Spelaren räknar aldrig själv.** Besättningen räknar och rapporterar.
2. **Varje bedömning har kvalitet** (`Quality`: dålig, osäker, god, säker) som
   härleds ur datan, t.ex. TMA-kovarians. Slumpa aldrig fram kvalitet.
3. **Sanning och kunskap hålls isär.** Bara sensorer (`sim/sonar.py`, och
   periskop/radar/aktiv sonar i stationerna) läser `World`. `Knowledge` byggs
   enbart från händelser på bussen och har ingen referens till världen.
   Rapporter får aldrig avslöja sanningens id:n (`DD1`, `T1` …).
4. **`sim/` importerar aldrig Textual.** Gränssnittet bor i `ui/`.
5. **Besättningen föreslår åtgärder** via `Station.suggest(..., order="…")`;
   kaptenen svarar `ja`/`nej`. **Vapenavfyring föreslås aldrig som ja-order.**
   Förslag om sådant kaptenen redan beordrat släpps (`Game.suggestion_redundant`,
   `Order.STANDING`). Vid tystnad (10 min) tar vakthavande initiativ ur
   stationernas `idle_proposals()`.
6. Fast tidssteg 1 s. All slump via seedade `random.Random` – inga globala `random.*`.

## Arkitektur i korthet
- **Sanningslager:** `world.py` (tick-ordning dokumenterad där), `ownship.py`,
  `enemy.py`, `weapons.py`, `environment.py`, `acoustics.py`, `entities.py`.
  Transienter/emissioner som skapas under ett tick blir hörbara nästa tick.
- **Stationer** (`sim/stations/`): en per system, ärver `Station`. Har `COMMANDS`
  (`CommandSpec`), `on_order`, `update`, `say`, `suggest`. Nya system = ny station
  i `DEFAULT_STATIONS`; `Game` ska inte behöva ändras.
- **Rapporter** bär `type` + `data`, aldrig färdig text. Texten skapas av
  `phrases.render()` vid leverans, efter rapportfiltren. Varje station registrerar
  sina fraser med `phrases.register({...})` i sin egen modul.
- **Händelsebussen** (`events.py`) är synkron. `Knowledge` registreras före
  stationerna så att stationer alltid ser uppdaterad kunskap.
- **Utbyggnadskrokar:** rapportfilter (`ReportQueue.filters`, ändrar `data`) för
  trötthet/lojalitet/sabotage; `CrewMember.effective_skill()` för all
  prestationspåverkan; prenumeration på `ReportDelivered` för tal (`say`).

## Kalibrering (ändra medvetet, kör sedan provspel)
- Språngskikt 60 m, 7 dB (`environment.py`). Kavitationsfart `6 + djup/25` kn.
- Jagare: källnivå `137 + 1,25·fart`; ping 230 dB; aktiv räckvidd ~4,4 nm över
  skiktet, ~2 nm under. Passivt hör den oss sällan om vi inte kaviterar.
- Egen ubåt: turbin 128 dB, smygmotor 112, reaktorpumpar 120 (går alltid när
  reaktorn är i drift). Vi hör jagaren på ~5–6 nm under skiktet i 5 kn.
- TMA: svaga antaganden (fart σ 30 kn, avstånd log-normal kring 6 nm), 30 min
  fönster, kvalitet ur σ_r/r (10/25/50 %), manöverdetektering vid chi² > 4.
  Två ben i sicksack ska normalt ge god/säker lösning på ~20 min.
- Provdjup 300 m, krossdjup 450 m, periskopdjup ≤ 18 m, antenndjup ≤ 30 m.

## Arbetssätt
- Bygg i steg och **committa efter varje steg** (användaren vill det). Vid större
  nya delar: föreslå struktur och invänta ok.
- Nytt system ⇒ tester i `tests/`. Statistiska påståenden (TMA, sonar) testas över
  flera seeds, inte ett enda lyckat frö.
- Verifiera spelkänslan med en huvudlös genomspelning: skapa `Game`, prenumerera
  på `ReportDelivered`, skriv ut rapporter, kör `g.tick()` i en loop (gärna med
  en bot som svarar `ja` på förslag). Skriv sådana skript i scratchpad, inte i repot.
- Gränssnittet kan provköras med `App.run_test()` och `save_screenshot()`.
- Sanningsloggen (`logs/truth-*.log`) visar exakta positioner, fiendens tillstånd
  och datum – använd den för felsökning.

## Fallgropar
- Döp aldrig en metod i en Textual-widget till `_render` (krockar med Textual).
- Timer-callbacks i `ui/app.py` kan köras under nedstängning – skydda mot `NoMatches`.
- Förslag spärras per nyckel med `cooldown`; glöm inte det, annars spammar
  besättningen.
- TMA antar rak kurs; om målet manövrerar ska plottlaget säga det och börja om
  (`ContactTrack.tma_from_t`), inte rapportera en orimlig lösning.
