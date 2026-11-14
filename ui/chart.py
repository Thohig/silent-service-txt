"""Sjökortet i helskärm (Tab eller "sjökort"). Spelet går vidare medan kortet visas."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Static

from sim.fmt import nm
from sim.reports import Report

from .chart_render import STYLE, fmt_grid, grid_step, render_chart
from .widgets import QUALITY_STYLE, ROLE_STYLE

ZOOM = (0.01, 0.025, 0.05, 0.1, 0.2, 0.4)          # sjömil per kolumn
DEFAULT_ZOOM = 3
PAN_COLS = 10
REDRAW_S = 0.25
TICKER_LINES = 2

LEGEND = [
    ("@", "own", "beräknad position"), ("·", "track", "bestick"), ("+", "fix", "fix"),
    ("◆", "contact", "lösning"), ("◇", "merchant", "handelsfartyg"),
    ("╲", "bearing", "bäring utan lösning"),
    ("⊕", "waypoint", "position från huvudstaben"), ("≈", "ice_open", "öppet vatten"),
    ("=", "ice_thin", "tunn is"), ("#", "ice_thick", "tjock is"), ("Ö", "opening", "öppning"),
    (".", "own", "osäkerhet"), ("╱", "contour", "djupkurva"), ("∙", "sounding", "ekolod"),
]

LEGEND_SPLIT = 7                  # andra raden: isen och osäkerheten


class ChartScreen(Screen):
    CSS = """
    ChartScreen { background: #0b0f0c; }
    #chart-head { height: 2; background: #1c2a20; color: #c8d0b0; }
    #chart-body { height: 1fr; }
    #chart-legend { height: 2; color: #7f9a80; }
    #chart-ticker { height: 2; background: #0f1611; }
    """
    BINDINGS = [
        Binding("escape", "close", "Tillbaka"),
        Binding("plus,equals_sign", "zoom(-1)", "Zooma in"),
        Binding("minus", "zoom(1)", "Zooma ut"),
        Binding("up", "pan(0,1)", show=False),
        Binding("down", "pan(0,-1)", show=False),
        Binding("left", "pan(-1,0)", show=False),
        Binding("right", "pan(1,0)", show=False),
        Binding("c", "center", "Centrera"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.zoom = DEFAULT_ZOOM
        self.follow = True
        self.center: tuple[float, float] = (0.0, 0.0)
        self.ticker: list[Text] = []

    def compose(self) -> ComposeResult:
        yield Static(id="chart-head")
        yield Static(id="chart-body")
        yield Static(_legend(), id="chart-legend")
        yield Static(id="chart-ticker")

    def on_mount(self) -> None:
        self.draw()
        self.set_interval(REDRAW_S, self.draw)

    @property
    def scale(self) -> float:
        return ZOOM[self.zoom]

    # --- tangenter ----------------------------------------------------------------
    def action_close(self) -> None:
        self.app.pop_screen()

    def action_zoom(self, step: int) -> None:
        self.zoom = min(max(self.zoom + step, 0), len(ZOOM) - 1)
        self.draw()

    def action_pan(self, dx: int, dy: int) -> None:
        cx, cy = self.center
        d = PAN_COLS * self.scale
        self.center = (cx + dx * d, cy + dy * 2 * d)
        self.follow = False
        self.draw()

    def action_center(self) -> None:
        self.follow = True
        self.draw()

    # --- ritning --------------------------------------------------------------------
    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#chart-body", Static)
            head = self.query_one("#chart-head", Static)
        except NoMatches:
            return
        view = game.chart()
        if self.follow:
            self.center = view.own
        w, h = body.size.width, body.size.height
        if w < 10 or h < 4:
            return
        lines = render_chart(view, *self.center, self.scale, w, h)
        body.update(Text("\n").join(lines))

        t = Text()
        t.append(" NAVIGATÖRENS SJÖKORT ", style="bold")
        t.append(f" {view.area_name} · {view.clock[:5]}")
        for n in view.notes:
            t.append(" · ")
            t.append(n.text, style=QUALITY_STYLE[n.quality] if n.quality else "")
        t.append("\n")
        t.append(f" 1 tecken = {_nm(self.scale)} nm · rutnät {fmt_grid(grid_step(self.scale))} nm"
                 f" · N↑", style="dim")
        t.append("   +/− zoom · pilar flyttar · c centrerar · Tab djupprofil · Esc tillbaka"
                 + ("" if self.follow else " · (ej centrerat)"), style="dim")
        head.update(t)

    def add_report(self, clock: str, report: Report) -> None:
        line = Text(f" {clock[:5]} ", style="dim")
        line.append(f"{report.speaker}: " if report.speaker else "",
                    style=ROLE_STYLE.get(report.role, "bold"))
        line.append(report.text or "", style="bold red" if report.alarm else "")
        self.ticker = (self.ticker + [line])[-TICKER_LINES:]
        try:
            self.query_one("#chart-ticker", Static).update(Text("\n").join(self.ticker))
        except NoMatches:
            pass


def _nm(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".").replace(".", ",") if v < 0.1 else nm(v)


def _legend() -> Text:
    t = Text(" ", no_wrap=True, overflow="crop")
    for i, (sym, style, what) in enumerate(LEGEND):
        if i == LEGEND_SPLIT:
            t.append("\n ")
        t.append(sym, style=STYLE[style])
        t.append(f" {what}  ", style="dim")
    return t
