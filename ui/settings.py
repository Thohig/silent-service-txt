"""Inställningar från huvudmenyn: ljud, talets språk och slumpfrö. Värdena bor i SubApp
(sound_wanted, language, fixed_seed) och gäller för alla uppdrag tills de ändras."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from .audio import RU_VOICE, MacPlayer

SOUND, SPEECH, SEED, BACK = "ljud", "tal", "fro", "tillbaka"
NAME_WIDTH = 12


def _row(name: str, value: str) -> Text:
    t = Text(f"{name:<{NAME_WIDTH}}", style="bold")
    t.append(value)
    return t


class SettingsScreen(Screen):
    DEFAULT_CSS = """
    SettingsScreen { background: #120b09; }
    SettingsScreen #settings-help, SettingsScreen #settings-title,
    SettingsScreen #settings-keys { background: #120b09; }
    SettingsScreen #settings-title { height: 3; padding: 1 2 0 2; color: #d8c8a0; }
    SettingsScreen #settings-body { height: 1fr; padding: 1 2 0 2; }
    SettingsScreen #settings-left { width: 40; }
    SettingsScreen #settings-list { height: auto; background: #120b09; border: none;
                                    color: #d8c8a0; scrollbar-size-vertical: 0; }
    SettingsScreen #settings-list > .option-list--option-highlighted {
        background: #4a1a12; color: #f4e6c4; }
    SettingsScreen #seed-input { border: tall #6a2a20; background: #1a100c; margin-top: 1; }
    SettingsScreen #seed-input:focus { border: tall #b8281c; }
    SettingsScreen #settings-help { width: 1fr; padding: 0 2 0 3; color: #d8c8a0;
                                    border-left: vkey #6a2a20; }
    SettingsScreen #settings-keys { height: 1; padding: 0 2; color: #8a7a5c; }
    """
    BINDINGS = [Binding("escape", "back", "Tillbaka")]

    def __init__(self) -> None:
        super().__init__()
        self.sound_available = MacPlayer.available()
        self.ru_voice = self.sound_available and MacPlayer.has_voice(RU_VOICE)

    def compose(self) -> ComposeResult:
        yield Static(Text("Inställningar", style="bold"), id="settings-title")
        with Horizontal(id="settings-body"):
            with Vertical(id="settings-left"):
                yield OptionList(*self._options(), id="settings-list")
                yield Input(placeholder="frö, tomt = slumpat", id="seed-input")
            yield Static("", id="settings-help")
        yield Static("↑ ↓ välj · Enter ändra · Esc tillbaka", id="settings-keys")

    def on_mount(self) -> None:
        self.query_one("#seed-input").display = False
        lst = self.query_one("#settings-list", OptionList)
        lst.highlighted = 0
        lst.focus()
        self._help(SOUND)

    # --- värden -----------------------------------------------------------------
    def _options(self) -> list[Option | None]:
        app = self.app
        sound = "på" if app.sound_wanted else "av"
        if not self.sound_available:
            sound += " (kräver macOS)"
        speech = "ryska" if app.language in (None, "ru") else "svenska"
        seed = "slumpat" if app.fixed_seed is None else str(app.fixed_seed)
        return [Option(_row("Ljud", sound), id=SOUND), Option(_row("Tal", speech), id=SPEECH),
                Option(_row("Slumpfrö", seed), id=SEED), None,
                Option(Text("Tillbaka", style="bold"), id=BACK)]

    def _refresh(self) -> None:
        lst = self.query_one("#settings-list", OptionList)
        at = lst.highlighted
        lst.clear_options()
        lst.add_options(self._options())
        lst.highlighted = at

    def _help(self, key: str | None) -> None:
        app = self.app
        if key == SOUND:
            t = Text("Tal, larm, hydrofonljud och bakgrundsljud. Går också att slå av och på "
                     "under spelet med ctrl+t.")
            if not self.sound_available:
                t.append("\n\nLjudet kräver macOS (say och afplay).", style="dim")
        elif key == SPEECH:
            t = Text("Besättningen kan tala ryska eller svenska. Loggen är alltid på svenska. "
                     "Under spelet: tal ryska, tal svenska.")
            if not self.ru_voice:
                t.append(f"\n\nRösten {RU_VOICE} saknas, så besättningen talar svenska. Lägg "
                         "till den under Systeminställningar › Hjälpmedel › Talat innehåll › "
                         "Systemröst.", style="dim")
        elif key == SEED:
            t = Text("Samma frö ger samma läge: fiendens start, väder, botten och besättningens "
                     "slump. Tomt ger ett nytt läge varje gång.")
            if app.last_seed is not None:
                t.append(f"\n\nSenaste uppdraget hade frö {app.last_seed}.", style="dim")
        else:
            t = Text("Tillbaka till huvudmenyn.", style="dim")
        self.query_one("#settings-help", Static).update(t)

    # --- händelser ----------------------------------------------------------------
    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        self._help(event.option.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        app = self.app
        key = event.option.id
        if key == SOUND:
            app.sound_wanted = not app.sound_wanted
            if hasattr(app, "menu_sound_sync"):
                app.menu_sound_sync()
        elif key == SPEECH:
            app.language = "sv" if app.language in (None, "ru") else "ru"
        elif key == SEED:
            inp = self.query_one("#seed-input", Input)
            inp.value = "" if app.fixed_seed is None else str(app.fixed_seed)
            inp.display = True
            inp.focus()
            return
        elif key == BACK:
            self.action_back()
            return
        self._refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        text = event.value.strip()
        if text and not text.isdigit():
            event.input.value = ""
            event.input.placeholder = "bara siffror, tomt = slumpat"
            return
        self.app.fixed_seed = int(text) if text else None
        self._close_input()
        self._refresh()

    def _close_input(self) -> None:
        inp = self.query_one("#seed-input", Input)
        inp.display = False
        inp.placeholder = "frö, tomt = slumpat"
        self.query_one("#settings-list").focus()

    def action_back(self) -> None:
        if self.query_one("#seed-input").display:
            self._close_input()
            return
        self.app.pop_screen()
