"""Huvudfönstret. Simuleringen tickar i realtid oberoende av inmatningen.

Skärmarna: huvudmenyn (MenuScreen) → spelet (GameScreen, med vyerna ovanpå) → huvudmenyn
när uppdraget är slut och kaptenen trycker Enter. Appen håller spelet, ljudet och
inställningarna; varje uppdrag får ett nytt Game, en ny buss och en ny sanningslogg.
"""
from __future__ import annotations

import random
import time
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Input

from sim.events import GameEnded, ReportDelivered, TimeScaleChanged
from sim.game import Game
from sim.fmt import fmt_course, kn
from sim.scenario import build_scenario
from sim.truthlog import TruthLog

from .audio import SoundBoard, make_soundboard
from .chart import ChartScreen
from .logview import LogScreen
from .menu import MenuScreen
from .bridge import BridgeScreen
from .periscope import PeriscopeScreen
from .profile import ProfileScreen
from .systems import SystemScreen
from .teletype import Teletype
from .widgets import CentralView, DepthGauge, ReportLog, StatusBar

MAX_TICKS_PER_FRAME = 20
CHART_WORDS = {"sjökort", "sjokort", "kort", "karta"}
PROFILE_WORDS = {"profil", "djupprofil", "sidovy"}
SYSTEM_WORDS = {"system", "systemtavla", "systemtavlan", "tavla", "tavlan"}
PERISCOPE_WORDS = {"periskopbild", "periskopvy", "bild"}
BRIDGE_WORDS = {"brygga", "bryggan", "bryggvy", "utsikt"}
LOG_WORDS = {"logg", "loggen", "loggbok", "loggboken"}
CENTRAL_WORDS = {"central", "centralen"}
VIEWS = (LogScreen, ChartScreen, ProfileScreen, SystemScreen, PeriscopeScreen,
         BridgeScreen)
GAUGE_EVERY_S = 0.5
CENTRAL_MIN_WIDTH = 100                # smalare terminal: bara djupmätaren
BIG_MIN = (120, 36)                    # minst så stort: centralen är huvudvyn, loggen en remsa
SOUND_WORDS = {"ljud", "ljud av", "ljud på", "ljud pa"}
SPEECH_WORDS = {"tal ryska": "ru", "tal svenska": "sv"}
SOUND_KEY = "ctrl+t"                   # t som i tal


FRAME_S = 0.05
OVER_PLACEHOLDER = "Uppdraget är slut – Enter: tillbaka till huvudmenyn"


class GameScreen(Screen):
    """Spelets huvudskärm: statusrad, fjärrskrivaren, loggen, djupmätaren och orderraden.
    Logiken bor i SubApp; vyerna läggs ovanpå den här skärmen."""

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status")
        yield Teletype("", id="intro")
        with Vertical(id="main"):
            yield CentralView(id="central-big")
            with Horizontal(id="lower"):
                yield ReportLog(id="log", wrap=True, markup=False, max_lines=2000)
                with Vertical(id="side"):
                    yield CentralView(id="central")
                    yield DepthGauge(id="gauge")
        yield Input(placeholder="Order …   (skriv hjälp för en lista)", id="order")

    def on_mount(self) -> None:
        self.query_one("#main").display = False
        self.app._begin()

    def on_resize(self, event) -> None:
        """Stort fönster: centralen fyller vyn och loggen blir en remsa (hela loggen i loggvyn).
        Mindre: loggen stor och en liten central bredvid; smalt: bara djupmätaren."""
        w, h = event.size.width, event.size.height
        big = w >= BIG_MIN[0] and h >= BIG_MIN[1]
        self.set_class(big, "big")
        self.set_class(not big and w < CENTRAL_MIN_WIDTH, "narrow")

    @property
    def big(self) -> bool:
        return self.has_class("big")


class SubApp(App):
    TITLE = "K-114"
    CSS = """
    Screen { background: #0b0f0c; }
    #status { height: 2; background: #1c2a20; color: #c8d0b0; }
    #intro  { height: 1fr; padding: 2 6; }
    #main   { height: 1fr; }
    #central-big { height: 1fr; display: none; background: #0b0f0c; }
    #lower  { height: 1fr; }
    GameScreen.big #central-big { display: block; }
    GameScreen.big #lower { height: 11; }
    GameScreen.big #central { display: none; }
    GameScreen.big #side { width: 26; }
    GameScreen.narrow #central { display: none; }
    #log    { width: 1fr; padding: 0 1; background: #0b0f0c; scrollbar-size-vertical: 1; }
    #side   { width: 42; background: #0f1611; }
    GameScreen.narrow #side { width: 24; }
    #central { height: 13; padding: 0 1; }
    #gauge  { width: 100%; height: 1fr; padding: 1 1 0 1; background: #0f1611; color: #7f9a80; }
    #order  { border: tall #2f4a36; background: #0f1611; }
    #order:focus { border: tall #5f8a66; }
    """
    BINDINGS = [Binding("ctrl+q", "quit", "Avsluta", priority=True),
                Binding("tab", "cycle", "Nästa vy", priority=True),
                Binding(SOUND_KEY, "sound", "Ljud", priority=True)]

    def __init__(self, seed: int | None = None, log_dir: Path | str = "logs",
                 scenario: str | None = None, sound: bool = False):
        """scenario: nyckel i SCENARIOS. Utan scenario börjar spelet med huvudmenyn.
        sound: tal och larm (macOS). Av som standard så att testerna är tysta."""
        super().__init__()
        self.fixed_seed = seed               # inställning: samma frö varje uppdrag (None: slumpat)
        self.seed: int | None = None         # det pågående uppdragets frö
        self.last_seed: int | None = None
        self.log_dir = Path(log_dir)
        self.game: Game | None = None
        self.truth_log: TruthLog | None = None
        self.running = False
        # blickens sanna bäring, delad mellan bryggvyn och periskopvyn (None: inte satt)
        self.look_bearing: float | None = None
        self._game_ready = False             # spelet är klart att ta över (efter ev. uppvärmning)
        self._acc = 0.0
        self._last = 0.0
        self.sound_wanted = sound
        self.sound: SoundBoard | None = None
        self._sound_note: str | None = None
        self._gauge_t = 0.0
        self._spoke: dict[str, float] = {}   # roll → när den senast rapporterade (väggklocka)
        self.language: str | None = None     # talets språk, gäller över uppdragen
        self.scenario_key: str | None = None
        self._screen: GameScreen | None = None
        self._pump_timer: Timer | None = None
        if scenario is not None:
            self._create_game(scenario)

    def _create_game(self, key: str) -> None:
        self.seed = self.fixed_seed if self.fixed_seed is not None else random.randrange(1_000_000)
        self.last_seed = self.seed
        self.scenario_key = key
        scenario = build_scenario(key, random.Random(self.seed))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.log_dir / f"truth-{stamp}-{self.seed}.log"
        n = 2
        while path.exists():                 # samma frö igen inom samma sekund
            path = self.log_dir / f"truth-{stamp}-{self.seed}-{n}.log"
            n += 1
        self.truth_log = TruthLog(path)
        self.truth_log.write(f"# seed={self.seed} scenario={key}")
        # en kort variants uppvärmning körs i en tråd medan ordern skrivs ut (_begin)
        self.game = Game(scenario, seed=self.seed, truth_log=self.truth_log, warm_up=False)

    def gs(self) -> GameScreen:
        """Spelskärmen (även när en vy ligger ovanpå)."""
        if self._screen is None:
            raise NoMatches("ingen spelskärm")
        return self._screen

    def on_mount(self) -> None:
        if self.game is not None:            # --scenario: spelet skapades i __init__
            self._show_game()
        else:
            self.push_screen(MenuScreen())

    def start_scenario(self, key: str) -> None:
        """Huvudmenyn: skapa spelet och visa den hemliga ordern."""
        if self.game is not None:
            return
        self._create_game(key)
        self._show_game()

    def _show_game(self) -> None:
        self._screen = GameScreen()
        if isinstance(self.screen, MenuScreen):
            self.switch_screen(self._screen)
        else:
            self.push_screen(self._screen)       # _begin när skärmen är monterad

    def _begin(self) -> None:
        """Scenariot är valt: visa den hemliga ordern på fjärrskrivaren."""
        game = self.game
        gs = self.gs()
        gs.query_one(StatusBar).show(game.status())
        gs.query_one("#order", Input).focus()
        tt = gs.query_one(Teletype)
        tt.full_text = game.secret_order
        tt.start()
        if game.warmup_pending:
            self.run_worker(self._run_warmup, thread=True, exclusive=True, group="warmup")
        else:
            self._attach_game()

    def _run_warmup(self) -> None:
        """Tråd: vakten före kaptenen. Inget annat rör spelet förrän den är klar."""
        self.game.warm_up()
        self.call_from_thread(self._attach_game)

    def _attach_game(self) -> None:
        """Lyssna på spelet först nu, så att vaktens rapporter inte syns."""
        game = self.game
        game.bus.subscribe(ReportDelivered, self._on_report)
        game.bus.subscribe(TimeScaleChanged, self._on_time_scale)
        game.bus.subscribe(GameEnded, self._on_game_ended)
        self.sound, self._sound_note = make_soundboard(
            game.bus, self.sound_wanted, heading=lambda: game.status().course)
        if self.language is not None:
            self.sound.set_language(self.language)
        self._game_ready = True
        self._spoke = {}
        try:
            self.gs().query_one(StatusBar).show(game.status())
            self._show_central(game.status(), time.monotonic())
            if self.gs().query_one(Teletype).done:
                self._show_footer()
        except NoMatches:
            pass

    def _show_footer(self) -> None:
        self.gs().query_one(Teletype).set_footer(
            "Tryck Enter för att ta befälet." if self._game_ready
            else "Vakthavande gör klart vakten …")

    def on_teletype_finished(self, _: Teletype.Finished) -> None:
        self._show_footer()

    # ------------------------------------------------------------------ order
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if self.game is None:
            return
        if not self.running:
            tt = self.gs().query_one(Teletype)
            if not tt.done:
                tt.finish()
            elif self._game_ready:
                self._start()
            return
        if self._view_word(text.lower()):
            return
        if self.game.over:
            if not text:
                self.return_to_menu()
            else:
                self.gs().query_one(ReportLog).add_system(
                    self.game.clock_str(), "Uppdraget är slut. Enter tar dig tillbaka till huvudmenyn.")
            return
        if not text:
            return
        if text.lower() in SOUND_WORDS:
            want = {"ljud av": False, "ljud på": True, "ljud pa": True}.get(text.lower())
            self.action_sound(want)
            return
        if text.lower() in SPEECH_WORDS:
            self.action_speech(SPEECH_WORDS[text.lower()])
            return
        self.gs().query_one(ReportLog).add_captain(self.game.clock_str(), text)
        if isinstance(self.screen, VIEWS):
            self.screen.add_captain(self.game.clock_str(), text)
        self.game.command(text)

    def _view_word(self, text: str) -> bool:
        """Ord som öppnar en vy (eller loggen). Sant om ordet var ett sådant."""
        if text in CHART_WORDS:
            self.action_chart()
        elif text in PROFILE_WORDS:
            self.action_profile()
        elif text in SYSTEM_WORDS:
            self.action_systems()
        elif text in PERISCOPE_WORDS:
            self.action_periscope()
        elif text in BRIDGE_WORDS:
            self.action_bridge()
        elif text in LOG_WORDS:
            if self.gs().big:
                self._toggle_view(LogScreen)
            elif isinstance(self.screen, VIEWS):
                self.pop_screen()
        elif text in CENTRAL_WORDS:
            if isinstance(self.screen, VIEWS):
                self.pop_screen()
        else:
            return False
        return True

    def _start(self) -> None:
        self.gs().query_one(Teletype).display = False
        self.gs().query_one("#main").display = True
        log = self.gs().query_one(ReportLog)
        st = self.game.world.own.state
        log.add_system(self.game.clock_str(),
                       f"Du har befälet. Ubåten går kurs {fmt_course(st.course)}, "
                       f"fart {kn(st.speed)} knop, djup {st.depth:.0f} meter.")
        log.add_system(self.game.clock_str(), "Skriv hjälp för en lista över order. Besättningens förslag godkänns med ja, avslås med nej.")
        if self.sound is not None and self.sound.enabled and self.sound.speaks_russian:
            log.add_system(self.game.clock_str(), "Besättningen talar ryska, loggen är på svenska. "
                           "tal svenska byter språk.")
        if self.gs().big:
            log.add_system(self.game.clock_str(), "Tab växlar mellan centralen, loggboken, sjökort, "
                           "djupprofil, systemtavla och periskopbild, i ytläge också bryggan.")
        else:
            log.add_system(self.game.clock_str(), "Tab växlar mellan logg, sjökort, djupprofil, "
                           "systemtavla och periskopbild, i ytläge också bryggan.")
        if self._sound_note:
            log.add_system(self.game.clock_str(), self._sound_note)
        elif self.sound and self.sound.enabled:
            log.add_system(self.game.clock_str(), "ctrl+t slår av och på ljudet.")
        self.running = True
        self._last = time.monotonic()
        self._pump_timer = self.set_interval(FRAME_S, self._pump)

    # ------------------------------------------------------------------ vyer
    def _toggle_view(self, cls: type[Screen]) -> None:
        """Visa eller stäng en helskärmsvy. Spelet går vidare under tiden."""
        if not self.running or self.game is None:
            return
        if isinstance(self.screen, cls):
            self.pop_screen()
            return
        if isinstance(self.screen, VIEWS):
            self.pop_screen()
        self.push_screen(cls())

    def action_chart(self) -> None:
        self._toggle_view(ChartScreen)

    def action_profile(self) -> None:
        self._toggle_view(ProfileScreen)

    def action_systems(self) -> None:
        self._toggle_view(SystemScreen)

    def action_periscope(self) -> None:
        self._toggle_view(PeriscopeScreen)

    def action_bridge(self) -> None:
        self._toggle_view(BridgeScreen)

    def tab_views(self) -> tuple[type[Screen], ...]:
        """Tab-ordningen efter läget: under ytan ingen brygga; med folk på väg upp eller på
        bryggan kommer bryggan före periskopbilden (kikaren)."""
        base = (ChartScreen, ProfileScreen, SystemScreen)
        if self._screen is not None and self._screen.big:
            base = (LogScreen,) + base
        if self.game is None or self.game.status().bridge == "shut":
            return base + (PeriscopeScreen,)
        return base + (BridgeScreen, PeriscopeScreen)

    def action_cycle(self) -> None:
        """Tab: huvudvyn → (loggboken, om centralen är huvudvy) → sjökort → djupprofil →
        systemtavla → periskop (och brygga) → huvudvyn."""
        if not self.running or self.game is None:
            return
        views = self.tab_views()
        cur = next((i for i, cls in enumerate(views) if isinstance(self.screen, cls)), None)
        if cur is None and isinstance(self.screen, VIEWS):
            cur = len(views) - 1            # en vy utanför ordningen (bryggan under ytan)
        if cur is None:
            self._toggle_view(views[0])
        elif cur + 1 < len(views):
            self._toggle_view(views[cur + 1])
        else:
            self.pop_screen()

    # ------------------------------------------------------------------ ljud
    def action_sound(self, want: bool | None = None) -> None:
        """ctrl+t eller "ljud": slå av och på tal och larm."""
        if not self.running or self.sound is None:
            return
        if not self.sound.available:
            self.gs().query_one(ReportLog).add_system(
                self.game.clock_str(), self._sound_note or "Ljudet är avstängt (--tyst).")
            return
        if want is None or want != self.sound.enabled:
            self.sound.toggle()
        self.sound_wanted = self.sound.enabled
        self.gs().query_one(ReportLog).add_system(
            self.game.clock_str(), "Ljudet på." if self.sound.enabled else "Ljudet av.")

    def action_speech(self, language: str) -> None:
        """"tal ryska" / "tal svenska": vilket språk besättningen talar. Loggen är alltid svensk."""
        if self.sound is None:
            return
        russian = self.sound.set_language(language)
        self.language = language
        if language == "ru" and not russian:
            msg = ("Rösten Milena saknas, besättningen talar svenska. Lägg till den under "
                   "Systeminställningar › Hjälpmedel › Talat innehåll › Systemröst.")
        else:
            msg = "Besättningen talar ryska. Loggen är på svenska." if russian \
                else "Besättningen talar svenska."
        self.gs().query_one(ReportLog).add_system(self.game.clock_str(), msg)

    # ------------------------------------------------------------------ realtid
    def _pump(self) -> None:
        if not self.is_running or self.game is None:
            return
        now = time.monotonic()
        if self.sound:
            self.sound.update(now)          # slutrapporten läses upp även när spelet är slut
        if self.game.over:
            if self.sound:
                self.sound.ambient(None)
            return
        self._acc += (now - self._last) * self.game.time_scale
        self._last = now
        n = 0
        while self._acc >= 1.0 and n < MAX_TICKS_PER_FRAME:
            scale_before = self.game.time_scale
            self.game.tick()
            self._acc -= 1.0
            n += 1
            if self.game.time_scale < scale_before:
                self._acc = 0.0      # larm: släpp resterande komprimerad tid
                break
        self._acc = min(self._acc, 2.0)
        status = self.game.status()
        if self.sound:
            self.sound.ambient(status, self.game.knowledge.tracks.values())
        try:
            self.gs().query_one(StatusBar).show(status)
            if now - self._gauge_t >= GAUGE_EVERY_S:
                self._gauge_t = now
                self.gs().query_one(DepthGauge).show(self.game.profile())
                self._show_central(status, now)
        except NoMatches:
            pass

    def _show_central(self, status, now: float) -> None:
        gs = self.gs()
        speaking = {role: now - t for role, t in self._spoke.items()}
        view = gs.query_one("#central-big" if gs.big else "#central", CentralView)
        if view.display:
            view.show(status, speaking, now)

    # ------------------------------------------------------------------ händelser
    def _on_report(self, e: ReportDelivered) -> None:
        self._spoke[e.report.role] = time.monotonic()
        self.gs().query_one(ReportLog).add_report(self.game.clock_str(), e.report)
        if isinstance(self.screen, VIEWS):
            self.screen.add_report(self.game.clock_str(), e.report)

    def _on_time_scale(self, e: TimeScaleChanged) -> None:
        log = self.gs().query_one(ReportLog)
        if e.reason == "larm":
            log.add_system(self.game.clock_str(), "Tidskomprimering avbruten – 1×.", "bold red")
        else:
            log.add_system(self.game.clock_str(), f"Tidskomprimering {e.scale}×.")
        self.gs().query_one(StatusBar).show(self.game.status())

    def _on_game_ended(self, e: GameEnded) -> None:
        if isinstance(self.screen, VIEWS):
            self.pop_screen()               # slutrapporten visas i loggen
        gs = self.gs()
        gs.query_one(ReportLog).add_ending(e.summary)
        if gs.big:
            self.push_screen(LogScreen())    # slutrapporten får inte plats i remsan
        inp = gs.query_one("#order", Input)
        inp.placeholder = OVER_PLACEHOLDER
        inp.focus()
        gs.query_one(StatusBar).show(self.game.status())

    def return_to_menu(self) -> None:
        """Uppdraget är slut: stäng spelet och visa huvudmenyn med samma scenario markerat."""
        key = self.scenario_key
        self._close_game()
        while isinstance(self.screen, VIEWS):
            self.pop_screen()
        self.switch_screen(MenuScreen(selected=key))

    def _close_game(self) -> None:
        if self._pump_timer is not None:
            self._pump_timer.stop()
            self._pump_timer = None
        if self.sound:
            self.sound.close()
            self.sound = None
        if self.truth_log:
            self.truth_log.close()
            self.truth_log = None
        self.game = None
        self._screen = None
        self.running = False
        self._game_ready = False
        self.look_bearing = None
        self._acc = 0.0

    def on_unmount(self) -> None:
        if self.sound:
            self.sound.close()
        if self.truth_log:
            self.truth_log.close()
