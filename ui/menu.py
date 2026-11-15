"""Huvudmenyn: uppdragen grupperade med sina varianter, beskrivningen av det markerade bredvid.

Spelaren kommer tillbaka hit när ett uppdrag är slut. Grupperingen härleds ur scenarierna:
en kort variants nyckel är det långa scenariots nyckel plus "-x" (`kuba`, `kuba-kort`), och
titeln är "Rubrik – variant, datum". Övningen står först, sedan i registreringsordning.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sim.scenario import SCENARIOS, ScenarioDef

FIRST_GROUPS = ("ovning",)        # övningen först: den lär känna båten
QUIT_ID = "_avsluta"
SHORT_PREFIX = "Kort variant. "
LIST_WIDTH = 44
LABEL_WIDTH = 26


@dataclass
class MissionGroup:
    key: str                      # det långa scenariots nyckel
    heading: str                  # "Kvadrat 7"
    date: str                     # "oktober 1962"
    variants: list[ScenarioDef] = field(default_factory=list)

    @property
    def main(self) -> ScenarioDef:
        """Det långa scenariot (utan speltid), annars det första."""
        return next((sd for sd in self.variants if sd.minutes is None), self.variants[0])


def split_title(title: str) -> tuple[str, str | None, str]:
    """"Kvadrat 7 – sambandsfönstret, oktober 1962" ⇒ ("Kvadrat 7", "sambandsfönstret", "oktober 1962")."""
    name, _, date = title.partition(", ")
    heading, _, variant = name.partition(" – ")
    return heading, (variant or None), date


def mission_groups() -> list[MissionGroup]:
    groups: dict[str, MissionGroup] = {}
    for sd in SCENARIOS.values():
        gk = sd.key.split("-")[0]
        if gk not in groups:
            groups[gk] = MissionGroup(gk, "", "")
        groups[gk].variants.append(sd)
    for g in groups.values():
        g.variants.sort(key=lambda sd: (sd.minutes is not None, list(SCENARIOS).index(sd.key)))
        g.heading, _, g.date = split_title(g.main.title)
    first = [groups[k] for k in FIRST_GROUPS if k in groups]
    return first + [g for k, g in groups.items() if k not in FIRST_GROUPS]


def variant_label(sd: ScenarioDef) -> Text:
    _, variant, _ = split_title(sd.title)
    label = variant or "hela uppdraget"
    length = f"~{sd.minutes} min" if sd.minutes else "lång"
    t = Text("  " + label[:LABEL_WIDTH].ljust(LABEL_WIDTH))
    t.append(length.rjust(9), style="dim")
    return t


def heading_label(g: MissionGroup) -> Text:
    t = Text(g.heading, style="bold")
    t.append("  " + g.date, style="dim")
    return t


def brief(sd: ScenarioDef, group: MissionGroup | None) -> Text:
    """Beskrivningen till höger om listan."""
    t = Text(sd.title, style="bold")
    t.append("\n")
    short = sd.minutes is not None
    t.append((f"Kort variant · ~{sd.minutes} min" if short else "Hela uppdraget · flera timmar")
             + "\n\n", style="dim")
    summary = sd.summary.removeprefix(SHORT_PREFIX) if short else sd.summary
    t.append(summary)
    if short and group is not None and group.main is not sd:
        t.append("\n\nUppdraget i sin helhet\n", style="bold dim")
        t.append(group.main.summary, style="italic dim")
    others = [o for o in (group.variants if group else []) if o is not sd]
    if others:
        t.append("\n\nAndra varianter: ", style="dim")
        t.append(", ".join(split_title(o.title)[1] or "hela uppdraget" for o in others),
                 style="dim")
    t.append("\n\nEnter tar dig till den hemliga ordern.", style="dim")
    return t


class MenuScreen(Screen):
    """Huvudmenyn. selected: scenariot som markeras (det man nyss spelade)."""

    DEFAULT_CSS = """
    MenuScreen { background: #0b0f0c; }
    MenuScreen #menu-title { height: 3; padding: 1 2 0 2; color: #c8d0b0; }
    MenuScreen #menu-body  { height: 1fr; padding: 1 2 0 2; }
    MenuScreen #scenarios  { width: %d; height: 1fr; background: #0b0f0c; border: none;
                             color: #c8d0b0; scrollbar-size-vertical: 1; }
    MenuScreen #scenarios > .option-list--option-disabled { color: #c8d0b0; }
    MenuScreen #scenarios > .option-list--option-highlighted { background: #2f4a36; color: #e8f0d0; }
    MenuScreen #brief      { width: 1fr; height: 1fr; padding: 0 2 0 3; color: #c8d0b0;
                             border-left: vkey #2f4a36; }
    MenuScreen #menu-keys  { height: 1; padding: 0 2; color: #7f9a80; }
    """ % LIST_WIDTH

    def __init__(self, selected: str | None = None) -> None:
        super().__init__()
        self.selected = selected
        self.groups = mission_groups()
        self._group_of = {sd.key: g for g in self.groups for sd in g.variants}

    def compose(self) -> ComposeResult:
        title = Text("K-114", style="bold")
        title.append("   Projekt 627A · Norra flottan · oktober 1962", style="dim")
        yield Static(title, id="menu-title")
        options: list[Option | None] = []
        for g in self.groups:
            if options:
                options.append(None)
            options.append(Option(heading_label(g), id=f"_grupp_{g.key}", disabled=True))
            options += [Option(variant_label(sd), id=sd.key) for sd in g.variants]
        options += [None, Option(Text("Avsluta", style="bold"), id=QUIT_ID)]
        with Horizontal(id="menu-body"):
            yield OptionList(*options, id="scenarios")
            yield Static("", id="brief")
        yield Static("↑ ↓ välj · Enter starta · ctrl+q avsluta", id="menu-keys")

    def on_mount(self) -> None:
        options = self.query_one("#scenarios", OptionList)
        key = self.selected if self.selected in SCENARIOS else self.groups[0].variants[0].key
        options.highlighted = options.get_option_index(key)
        options.focus()
        self._show(key)

    def _show(self, key: str | None) -> None:
        brief_w = self.query_one("#brief", Static)
        if key in SCENARIOS:
            brief_w.update(brief(SCENARIOS[key], self._group_of.get(key)))
        elif key == QUIT_ID:
            brief_w.update(Text("Stäng programmet.", style="dim"))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        self._show(event.option.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option.id == QUIT_ID:
            self.app.exit()
        elif event.option.id in SCENARIOS:
            self.app.start_scenario(event.option.id)
