"""Loggboken som lager: PageUp i vilken vy som helst fäller ned den över vyns nedre del.

Loggboken var en egen vy (Tab, "logg"). Nu ligger den över den vy som är öppen, ovanför orderraden,
så att kaptenen kan läsa bakåt och ge order utan att lämna sjökortet eller periskopet. Den visar hela
loggen ur huvudskärmens `ReportLog` (`entries`) och nya rader speglas dit medan den är nere.

PageUp: ned (första gången står den sist), sedan en sida bakåt. PageDown: en sida framåt, och förbi
sista raden fälls den upp. Esc (tom orderrad) fäller upp den. "logg" växlar den, "telegram" visar
bara remsorna (ordern, stabens radiogram, Radio Moskva); slutrapporten fäller ned den i full höjd.
Bokstäver går aldrig hit: de är orderradens (`läget`, `länsa` … skulle annars fälla ned loggen).
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Static

from .menutext import DIM
from .placards import view_title
from .strips import TelegramStrip
from .widgets import ReportLog

NO_TELEGRAMS = ("Inget mottaget än. Staben sänder vid sambandstillfällena (antenndjup); "
                "Radio Moskva hörs med radio moskva.")
ORDER_ROWS = 3              # orderraden (med ram) under lagret
SHARE = 0.7                 # så stor del av höjden ovanför orderraden lagret tar
MIN_ROWS = 6


class DrawerLog(ReportLog):
    """Lagrets kopia av loggen: med `only_telegrams` skrivs bara remsorna."""

    only_telegrams = False

    def emit(self, content) -> None:
        if self.only_telegrams and not isinstance(content, TelegramStrip):
            return
        super().emit(content)


class LogDrawer(Vertical):
    """Lagret. Läggs på skärmen när det fälls ned och tas bort när det fälls upp."""

    DEFAULT_CSS = """
    LogDrawer { overlay: screen; position: absolute; width: 100%; background: #0b0f0c;
                border-top: heavy #5f8a66; }
    LogDrawer #drawer-head { height: 1; background: #1c2a20; color: #c8d0b0; }
    LogDrawer #drawer-log { height: 1fr; padding: 0 1; background: #0b0f0c; scrollbar-size-vertical: 1; }
    """
    can_focus = False

    def __init__(self, telegrams: bool = False, full: bool = False) -> None:
        super().__init__(id="log-drawer")
        self.only_telegrams = telegrams
        self.full = full                      # slutrapporten: hela höjden ovanför orderraden
        self._strips = 0

    def compose(self) -> ComposeResult:
        yield Static(id="drawer-head")
        yield DrawerLog(id="drawer-log", wrap=True, markup=False, max_lines=2000)

    def on_mount(self) -> None:
        self.place()
        self.call_after_refresh(self.fill)    # när bredden är känd: remsorna bryts efter den
        main = self._main()
        if main is not None:
            main.mirror = self.query_one(DrawerLog)

    def on_unmount(self) -> None:
        main = self._main()
        try:
            mine = self.query_one(DrawerLog)
        except NoMatches:
            return
        if main is not None and main.mirror is mine:
            main.mirror = None

    def _main(self) -> ReportLog | None:
        try:
            return self.app.gs().query_one("#log", ReportLog)
        except (NoMatches, AttributeError):
            return None

    def place(self) -> None:
        """Ovanför orderraden, SHARE av höjden (full: hela)."""
        h = self.screen.size.height
        free = max(MIN_ROWS, h - ORDER_ROWS)
        rows = free if self.full else max(MIN_ROWS, round(free * SHARE))
        self.styles.height = rows
        self.styles.offset = (0, max(0, free - rows))

    def fill(self) -> None:
        """Skriv om lagret ur huvudloggen, med eller utan filtret, och stå sist."""
        main = self._main()
        try:
            log = self.query_one(DrawerLog)
        except NoMatches:
            return
        if main is None:
            return
        log.clear()
        log.entries = []
        log.only_telegrams = self.only_telegrams
        for entry in main.entries:
            log.emit(entry)
        self._strips = sum(isinstance(e, TelegramStrip) for e in main.entries)
        if self.only_telegrams and not self._strips:
            log.write(Text(NO_TELEGRAMS, style=f"italic {DIM}"))
        log.scroll_end(animate=False)
        self.draw()

    def draw(self) -> None:
        main = self._main()
        if main is None:
            return
        n = sum(isinstance(e, TelegramStrip) for e in main.entries)
        if self.only_telegrams and n and not self._strips:
            self.fill()                       # tomt filter som fått sin första remsa
            return
        self._strips = n
        t = view_title("LOGGBOKEN")
        if self.only_telegrams:
            t.append(f"  bara telegram ({n})", style="bold")
            t.append("   logg: allt", style="dim")
        else:
            t.append("   telegram: bara remsor", style="dim")
        t.append("   PgUp/PgDn · Esc upp", style="dim")
        try:
            self.query_one("#drawer-head", Static).update(t)
        except NoMatches:
            pass

    def set_telegrams(self, on: bool) -> None:
        self.only_telegrams = on
        self.fill()

    @property
    def log(self) -> DrawerLog:
        return self.query_one(DrawerLog)

    def at_end(self) -> bool:
        log = self.log
        return log.scroll_y >= log.max_scroll_y - 0.5


# --- på skärmen ------------------------------------------------------------------------
def drawer_on(screen: Screen) -> LogDrawer | None:
    try:
        return screen.query_one(LogDrawer)
    except NoMatches:
        return None


def open_drawer(screen: Screen, telegrams: bool = False, full: bool = False) -> LogDrawer:
    """Fäll ned lagret (eller byt filter på det som är nere)."""
    d = drawer_on(screen)
    if d is not None:
        if d.only_telegrams != telegrams:
            d.set_telegrams(telegrams)
        if d.full != full:
            d.full = full
            d.place()
        return d
    d = LogDrawer(telegrams=telegrams, full=full)
    screen.mount(d)
    return d


def close_drawer(screen: Screen) -> bool:
    d = drawer_on(screen)
    if d is None:
        return False
    d.remove()
    return True


def page_up(screen: Screen) -> None:
    d = drawer_on(screen)
    if d is None:
        open_drawer(screen)
        return
    d.log.scroll_page_up(animate=False)


def page_down(screen: Screen) -> None:
    d = drawer_on(screen)
    if d is None:
        return
    if d.at_end():
        close_drawer(screen)
    else:
        d.log.scroll_page_down(animate=False)
