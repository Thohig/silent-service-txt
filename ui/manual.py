"""Order och ordlista: det kaptenen kan säga, ordnat efter vem som utför det, och besättningens
ryska ord. Visas från huvudmenyn. Orderna hämtas ur stationernas COMMANDS, så ett nytt system
hamnar här av sig självt."""
from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from sim.crew import ROLE_LABEL
from sim.orders import HELP_COMMAND, QUIT_COMMAND, SUGGESTION_COMMANDS, TIME_COMMAND
from sim.russian import WORDS
from sim.stations import DEFAULT_STATIONS

from .views import manual_words

# gränssnittets egna ord (vyerna ur registret i ui/views.py, ljudet i ui/app.py) och tangenter
VIEW_WORDS = manual_words()
SOUND_WORDS = ["ljud", "tal ryska", "tal svenska", "tal viktigt", "tal allt", "tal larm", "tal av"]
KEYS = [("Tab", "nästa vy"), ("Esc", "tillbaka till huvudvyn"),
        ("PageUp", "loggboken över vyn, bläddra bakåt (PageDown framåt, Esc upp)"), ("ctrl+t", "ljud av och på"),
        ("ctrl+q", "stäng programmet")]


def order_sections() -> list[tuple[str, list[str]]]:
    """(rubrik, order) per roll i stationernas ordning, sist allmänna order."""
    sections: dict[str, list[str]] = {}
    for cls in DEFAULT_STATIONS:
        helps = [s.help for s in cls.COMMANDS if s.help]
        if helps:
            sections.setdefault(ROLE_LABEL[cls.role], []).extend(helps)
    general = [s.help for s in (*SUGGESTION_COMMANDS, TIME_COMMAND, HELP_COMMAND, QUIT_COMMAND)
               if s.help]
    return list(sections.items()) + [("Allmänt", general)]


def _grid(rows: list[tuple[str, str]], first: int = 13) -> Table:
    """Två kolumner: rubriken fast till vänster, texten bryts under sig själv."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", width=first, no_wrap=True)
    grid.add_column()
    for a, b in rows:
        grid.add_row(a, b)
    return grid


def manual_text() -> Group:
    words = Table.grid(padding=(0, 2))
    words.add_column(style="bold", no_wrap=True)
    words.add_column(style="dim", no_wrap=True)
    words.add_column()
    for w in WORDS.values():
        words.add_row(w.latin, w.cyrillic, w.meaning)
    return Group(
        Text("Order", style="bold"),
        Text("Flera order på en rad: kurs 090, fart 5; djup 100 (eller \"och\"). "
             "Besättningens förslag godkänns med ja (j) och avslås med nej (n). Frågar en station om "
             "din egen order svarar du ja i stället för att upprepa den. En felstavad order ger "
             "\"Menade ni …?\", och ja verkställer det.\n", style="dim"),
        _grid([(h, " · ".join(helps)) for h, helps in order_sections()]),
        Text("\nVyer och ljud", style="bold"),
        _grid([("Vyer", " · ".join(VIEW_WORDS)), ("Ljud", " · ".join(SOUND_WORDS)), *KEYS]),
        Text("\nRyska ord", style="bold"),
        Text("Besättningen talar ryska när talet är på ryska. Loggen är alltid på svenska.\n",
             style="dim"),
        words,
    )


class ManualScreen(Screen):
    """Order och ordlista. Esc eller Enter tillbaka till huvudmenyn."""

    DEFAULT_CSS = """
    ManualScreen { background: #120b09; }
    ManualScreen #manual-title { height: 3; padding: 1 2 0 2; color: #d8c8a0; }
    ManualScreen #manual-scroll { height: 1fr; padding: 1 2 0 2; scrollbar-size-vertical: 1;
                                  scrollbar-color: #6a2a20; scrollbar-background: #120b09; }
    ManualScreen #manual-body { color: #d8c8a0; }
    ManualScreen #manual-keys { height: 1; padding: 0 2; color: #8a7a5c; }
    """
    BINDINGS = [Binding("escape", "back", "Tillbaka"), Binding("enter", "back", "Tillbaka")]

    def compose(self) -> ComposeResult:
        yield Static(Text("Order och ordlista", style="bold"), id="manual-title")
        with VerticalScroll(id="manual-scroll"):
            yield Static(manual_text(), id="manual-body")
        yield Static("↑ ↓ bläddra · Esc tillbaka", id="manual-keys")

    def on_mount(self) -> None:
        self.query_one("#manual-scroll").focus()

    def action_back(self) -> None:
        self.app.pop_screen()
