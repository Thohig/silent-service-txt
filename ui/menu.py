"""Huvudmenyn: välj scenario. Spelaren kommer tillbaka hit när ett uppdrag är slut."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sim.scenario import SCENARIOS


class MenuScreen(Screen):
    """Scenarioväljaren. selected: scenariot som markeras (det man nyss spelade)."""

    def __init__(self, selected: str | None = None) -> None:
        super().__init__()
        self.selected = selected

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Static("K-114 — välj scenario", id="picker-title")
            yield OptionList(*[Option(scenario_label(sd), id=sd.key)
                               for sd in SCENARIOS.values()], id="scenarios")

    def on_mount(self) -> None:
        options = self.query_one("#scenarios", OptionList)
        if self.selected in SCENARIOS:
            options.highlighted = list(SCENARIOS).index(self.selected)
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option.id is not None:
            self.app.start_scenario(event.option.id)


def scenario_label(sd) -> Text:
    t = Text(sd.title, style="bold")
    t.append(f"  ({sd.key})" + (f"  ~{sd.minutes} min" if sd.minutes else "") + "\n", style="dim")
    t.append(sd.summary, style="italic")
    return t
