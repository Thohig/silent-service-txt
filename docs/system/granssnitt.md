# Huvudmenyn och ljudet

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

- **Huvudmenyn** (`ui/menu.py`, `MenuScreen`): uppdragen grupperade (`mission_groups`: kort variants nyckel
  = lång nyckel + "-x", titeln "Rubrik – variant, datum", det långa först, `FIRST_GROUPS` övningen först),
  rubriker är avstängda alternativ, beskrivningen (`brief`) bredvid, sist Inställningar, Order och
  ordlista, Avsluta. Inställningar (`ui/settings.py`): ljud, talets språk, slumpfrö (`SubApp.sound_wanted`,
  `language`, `fixed_seed`; `--seed`/`--tyst` sätter startvärdena, fröet gäller alla uppdrag tills det
  ändras). Order och ordlista (`ui/manual.py`) hämtar orderna ur stationernas `COMMANDS` per roll. Nytt scenario hamnar
  i menyn av sig självt om nyckel och titel följer mönstret. Stämningen (`ui/menutext.py`): sidhuvud som
  hemlig handling på rött fält (ryska med svensk översättning), stämpel per uppdrag efter datumet
  (`stamp_for`: övning ДСП, före 22 okt СЕКРЕТНО, 22–26 СОВ. СЕКРЕТНО, 27– ОСОБОЙ ВАЖНОСТИ), fjärrskrivarremsa
  (`DISPATCHES`, `ticker_at(t)`: kalendern 1–28 okt, 24 tecken/s, börjar om) och stridsberedskapen i
  sidhuvudet efter meddelandet (ständig, höjd, krigsfara, full; de två sista blinkar). Den 28 okt följer
  spelets historia: kriget har börjat. Färger ockra/flaggrött (`BG`, `INK`, `RED` …), även inställningar och
  ordlista. Ljud (`ui/menu_audio.py`, `MenuSound`, bara med ljudet på): egen musik (kör i d-moll, hjärtslag
  i basen, klocka, horn andra varvet; 64 s), hamnen (vind, vågor, mistlur, knarr; 40 s) och fjärrskrivaren
  medan remsan skriver; slingorna är cirkulära (efterklangen viks runt). Syntesen (~2 s) i en tråd,
  `lru_cache`. `MenuMixer` (en `Ambience` med `extra`-kroken) lägger enstaka ljud ovanpå. Uppdrag valt ⇒
  `depart()`: telegrafklockan, musiken tonar bort, fjärrskrivaren låter medan ordern skrivs ut; stängs när
  kaptenen tar befälet. `ctrl+t` och Inställningar slår av och på (`SubApp.menu_sound_sync`).
  Radio Moskva (`BULLETINS`, `radio_at(t)`): påhittade sändningar efter 25 s och sedan var 95:e s, allt
  mer olycksbådande (den sista upprepas); remsan visar översättningen. Ljud: ratten (`synth_tuning`),
  kortvågsbrus, musiken sänks; rösten är Milena renderad (`voices.backend().render`) genom `radio_voice` (smalt band, fading).
  Utan Milena bara brus. Bilden (`ui/menu_scene.py`, `render_scene(cols, rows, t)`): К-114 vid kaj i
  braille under beskrivningen (10 rader, bara när fönstret är ≥ 34 rader): stjärnor, fjällen, kajen med kran
  och lampa, ubåten med röd stjärna och lanterna, glitter på vattnet, snö i vinden; ingen slump (`_hash`). Flödet: menyn → spelet (`GameScreen` i `ui/app.py`, vyerna ovanpå) →
  huvudmenyn. `SubApp` håller spelet, ljudet och inställningarna (ljud, talets språk) över uppdragen;
  widgetarna nås med `app.gs().query_one(...)` (`app.query_one` ser bara standardskärmen). Efter
  slutrapporten går vyerna att titta på; Enter med tom orderrad (även i en vy) ⇒ `return_to_menu()`:
  timern stoppas, ljud och sanningslogg stängs, `game = None`, menyn markerar scenariot. Nytt uppdrag =
  nytt `Game`, ny buss, nytt frö om inget är inställt, logg `truth-<tid>-<frö>.log`.
  Den hemliga ordern (`ui/telegram.py`) visas som chiffertelegram: `order_header` (ШИФРОГРАММА, mottagningsnr
  ur fröet, uppdragets stämpel, avsändaren ur orderns `FRÅN:`-rad via `staff_of`) och `order_signature` under
  texten när den är utskriven (`Teletype.header`/`signature`/`style`, ockra papper). Slutrapporten börjar med
  `report_header` (ДОНЕСЕНИЕ till samma stab, stämpeln; `ReportLog.add_ending(summary, header=...)`).
  `avbryt uppdraget`/`avsluta` ⇒ vakthavande frågar (`off.confirm_quit`, förslag `avbryt uppdraget
  bekräftat`), `ja` ⇒ utfallet `quit`.
- **Ljud** (`ui/audio.py`): `SoundBoard` lyssnar bara på bussen – `ReportDelivered` ger tal
  (rösterna i `ui/voices.py`, takt per roll) och larm (`CUE_BY_TYPE`); `SoundHeard` (med sensorns `se`) ger
  hydrofonljud panorerade efter relativ bäring (`TRANSIENT_SOUND`); `OwnSoundMade` ger egna
  ljud (ping, avfyring, skenmål, nödblåsning). Syntetiserade wav. Av som standard i `SubApp`.
  Spelaren (`make_soundboard`): `MixPlayer` när ljudströmmen går och talsyntesen finns i processen
  (`voices.MacSynth`), annars `MacPlayer` (`say`/`afplay`). `MixPlayer` lägger allt i mixern som enstaka ljud
  (`Ambience.oneshot`, märkt `("tal", n)` för repliken): talet renderas i en egen tråd (30–70 ms till ljud,
  rösterna värms vid start) och kan få effekt (`speech_effect`): `phone` för stationerna utanför centralen
  (`REMOTE_ROLES`: sonar, torped, maskin, radio) och starpom i hyttens telefon, `muffled` för centralen hörd
  från hytten (låg prioritet, släpps efter 4 s), `hushed` i tystnaden (`Report.data["hushed"]`, vakthavandes
  rapportfilter: lågt, det skarpa bortfiltrerat, förstärkning 0,5; i loggboken kursivt grått; larm ropas ändå).
  Bakgrundsljud (`ui/ambience.py`): `ambient_targets(status, tracks)` ur `StatusSnapshot`
  (inkl. `sea_noise`, `fire`, `smoke`, `ventilating`) och hållna kontaktspår; `Ambience`
  mixar sömlösa slingor i en sounddevice-ström. Kontaktljudet följer klassificeringen.
  Centralen: `aircon` (alltid med reaktorn, svagare vid tyst gång), `crew` (mummel bakom skotten; tyst vid
  smygmotor eller jagade), `dread` (lågt sväv: jagade 0,11, hållen klassad örlogskontakt med se > 10 0,05).
  Skeppsklockan slår glasen (`bells_for`, 1–8 per fyratimmarsvakt) vid varje halvtimme på spelklockan,
  inte vid tyst gång eller jakt (`SoundBoard._ship_bell`). Vid överlämnandet läser vakthavande ett utrop i
  högtalaren (`crew_announcement` i `ui/telegram.py`: övning, operation eller krig efter stämpeln;
  `SoundBoard.announce`, ryska med Milena annars svenska; översättningen i loggen).
