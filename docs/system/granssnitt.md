# Huvudmenyn och ljudet

Flyttat ur CLAUDE.md (2026-11-18). Arbetsreglerna står kvar där; här är hur systemen
fungerar och deras siffror. Uppdatera här när systemet ändras.

- **Huvudmenyn** (`ui/menu.py`, `MenuScreen`): uppdragen grupperade (`mission_groups`: kort variants nyckel
  = lång nyckel + "-x", titeln "Rubrik – variant, datum", det långa först; ett uppdrag kan vara bara kort) i
  avdelningar (`SECTIONS`, `ScenarioDef.section`): ÖVNING, KRISEN (fred, förbli oupptäckt), KRIGET (vapen fria),
  i den ordningen och inom avdelningen i registreringsordning; beskrivningen säger avdelningen. Rubriker och
  avdelningsrader är avstängda alternativ, beskrivningen (`brief`) bredvid, sist Inställningar, Order och
  ordlista, Avsluta. Inställningar (`ui/settings.py`): ljud, talets språk, uppläsning (talnivån, Enter växlar
  viktigt → larm → av → allt; se Talnivån nedan), slumpfrö (`SubApp.sound_wanted`, `language`, `speech_level`, `fixed_seed`; `--seed`/`--tyst` sätter startvärdena, fröet gäller alla uppdrag tills det
  ändras). Order och ordlista (`ui/manual.py`) hämtar orderna ur stationernas `COMMANDS` per roll. Nytt scenario hamnar
  i menyn av sig självt om nyckel och titel följer mönstret (avdelningen `section`, standard krisen). Stämningen (`ui/menutext.py`): sidhuvud som
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
  huvudmenyn. `SubApp` håller spelet, ljudet och inställningarna (ljud, talets språk, uppläsning) över uppdragen;
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
- **Ljud** (`ui/audio.py`): `SoundBoard` lyssnar bara på bussen – `ReportDelivered` ger tal (`spoken`: inte
  systemrader eller rapporter med tabell, utom de som säger `data["spoken"]`, svepets rad; och bara det
  talnivån släpper fram, se nedan)
  (rösterna i `ui/voices.py`, takt per roll) och larm (`CUE_BY_TYPE`); `SoundHeard` (med sensorns `se`) ger
  hydrofonljud panorerade efter relativ bäring (`TRANSIENT_SOUND`); `OwnSoundMade` ger egna
  ljud (ping, avfyring, skenmål, nödblåsning). Syntetiserade wav. Av som standard i `SubApp`.
  Spelaren (`make_soundboard`): `MixPlayer` när ljudströmmen går och talsyntesen finns i processen
  (`voices.MacSynth`), annars `MacPlayer` (`say`/`afplay`); i webbläsaren `WebPlayer` (ljuden i mixern, talet
  direkt med `voices.WebSpeech`, utan effekter; utgången `ambience.output()`, där `web/start.py` sätter
  `web_audio.WebOut`). `sound_available()` säger om ljud finns (macOS eller webbläsaren). `MixPlayer` lägger allt i mixern som enstaka ljud
  (`Ambience.oneshot`, märkt `("tal", n)` för repliken): talet renderas i en egen tråd (30–70 ms till ljud,
  rösterna värms vid start) och kan få effekt (`speech_effect`): `phone` för stationerna utanför centralen
  (`REMOTE_ROLES`: sonar, torped, maskin, radio) och starpom i hyttens telefon, `muffled` för centralen hörd
  från hytten (låg prioritet, släpps efter 4 s), `hushed` i tystnaden (`Report.data["hushed"]`, vakthavandes
  rapportfilter: lågt, det skarpa bortfiltrerat, förstärkning 0,5; i loggboken kursivt grått; larm ropas ändå).
  Bakgrundsljud (`ui/ambience.py`): `ambient_targets(status, tracks)` ur `StatusSnapshot`
  (inkl. `sea_noise`, `fire`, `smoke`, `ventilating`) och hållna kontaktspår; `Ambience`
  mixar sömlösa slingor i en sounddevice-ström (i webbläsaren `web/web_audio.py`: kön fylls 0,25 s fram från
  händelseslingan och en AudioWorklet spelar den). Kontaktljudet följer klassificeringen.
  Centralen: `aircon` (alltid med reaktorn, svagare vid tyst gång), `crew` (mummel bakom skotten; tyst vid
  smygmotor eller jagade), `dread` (lågt sväv: jagade 0,11, hållen klassad örlogskontakt med se > 10 0,05).
  Skeppsklockan slår glasen (`bells_for`, 1–8 per fyratimmarsvakt) vid varje halvtimme på spelklockan,
  inte vid tyst gång eller jakt (`SoundBoard._ship_bell`). Vid överlämnandet läser vakthavande ett utrop i
  högtalaren (`crew_announcement` i `ui/telegram.py`: övning, operation eller krig efter stämpeln;
  `SoundBoard.announce`, ryska med Milena annars svenska; översättningen i loggen).
- **Ljudet ombord och skadekontrollen** (`ui/ambience.py`, `ambient_targets`, 2026-11-25): statusraden bär
  `pumps` (bilge/trim), `leak_rate`, `repairing` (loud/quiet) och `hushed`. En läcka sprutar (`flooding`, efter
  inflödet), vatten utan läcka droppar och skvalpar i kölsvinet (`drip`), pumparna dunkar (`pumps`, länspumpen
  djupare än trimpumpen), reparationen slår mot stål (`repair`) eller filar tyst (`repair_quiet`), och i tystnad i
  båten står fläktarna (inget `aircon`). Alla hörs dämpade i hytten.
- **Talnivån** (`ui/audio.py`, `SoundBoard.level`, `wanted`, 2026-11-24): `tal viktigt` (standard), `tal allt`, `tal larm`,
  `tal av`; i inställningarna "Uppläsning" (`SubApp.speech_level`, gäller över uppdragen). Loggen har alltid allt, och
  larmljuden går oavsett nivå. `speech_rank`: 2 larm (`alarm`) och förslag, 0 rutin (`kind == "done"` utom
  `NOT_ROUTINE_TYPES`, och `ROUTINE_TYPES`: sonarens bäringar, "hörs igen", dagsljuset, trimmen klar …), annars 1.
  `allt` läser 0–2, `viktigt` 1–2, `larm` 2, `av` inget (inte heller högtalarutropen). Utom med `allt`: kvittenserna
  läses bara "Есть" (`SHORT_ACK_RU`; svenskt tal "Jest"), och samma typ från samma roll om samma kontakt
  (`data["designation"]`) läses inte igen inom 3 min speltid (`REPEAT_S`) om inte kvaliteten ändrats; larm och förslag
  upprepas alltid. Tidskomprimering: från ×2 (`COMPRESSED_SCALE`) tystnar rutinen, från ×8 (`FAST_SCALE`) allt utom
  larm och förslag. Mätningen i `kalibrering/README.md` (Siffrorna): viktigt läser upp 42 % mindre än allt (loggen oförändrad).
