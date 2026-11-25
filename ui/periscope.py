"""Periskopbilden, en del av utsikten (`ui/lookout.py`, Tab eller "utsikt"/"periskopbild").

Vyn visar utkikens bild (`Knowledge.periscope`), inte världen. Medan masten är uppe
kommer en ny bild varannan sekund och okularet står där periskopet är vänt
(`StatusSnapshot.periscope_train`): ← → vrider det (`vrid periskop …`, tar över ett svep),
mellanslag vänder det förut, ↓ fäller det. När masten är nere visas den senaste bilden
(nedtonad när den är gammal), ← → byter föremål i okularet och ↑ hissar periskopet.

I ytläge med bryggan bemannad är okularet kikaren på bryggan (↓ från panoramat, ↑ tillbaka): det
visar bryggans levande bild (`Knowledge.bridge`). Blickens bäring delas med panoramat
(`SubApp.look_bearing`): okularet öppnas mot det bryggan tittade på, och det valda föremålet blir
bryggans blick.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from sim.geo import angle_diff

from .periscope_render import (default_index, header, object_key, ordered_objects,
                               render_periscope)
TURN_STEP_DEG = 5


class PeriscopePane:
    """Periskopets okular i utsikten (`ui/lookout.py`); med bryggan bemannad kikarens okular."""

    KEYS = {"left": "p_select(-1)", "right": "p_select(1)", "up": "p_raise", "down": "p_lower",
            "space": "p_ahead", "plus": "p_power('hög')", "equals_sign": "p_power('hög')",
            "minus": "p_power('låg')"}
    GLASS_KEYS = {"left": "p_select(-1)", "right": "p_select(1)", "up": "okular(False)",
                  "space": "p_ahead"}          # (mellanslag: inget periskop, ingen effekt)

    def __init__(self, screen) -> None:
        self.screen = screen
        self.selected_key: str | None = None
        self._pic_t: int | None = None

    @property
    def app(self):
        return self.screen.app

    def draw_now(self) -> None:
        self.screen.draw()

    def _game(self):
        return getattr(self.app, "game", None)

    def _hand(self, text: str) -> None:
        """Kaptenens hand på periskopet: en order utan rad i loggen."""
        game = self._game()
        if game is not None:
            game.command(text)
            self.draw_now()

    def raise_(self) -> None:
        game = self._game()
        if game is not None and game.status().periscope != "hold":
            self._hand("periskop upp")

    def lower(self) -> None:
        game = self._game()
        if game is not None and game.status().periscope is not None:
            self._hand("periskop ned")

    def ahead(self) -> None:
        game = self._game()
        if game is not None and game.status().periscope is not None:
            self._hand(f"vrid periskop {round(game.status().course) % 360:03d}")

    def power(self, power: str) -> None:
        """+ hög och − låg förstoring när periskopet hålls uppe (kaptenens hand)."""
        game = self._game()
        if game is not None and game.status().periscope == "hold" and \
                game.status().periscope_optic != "kikare":
            self._hand(f"förstoring {power}")

    def select(self, step: int) -> None:
        game = self._game()
        if game is not None and (st := game.status()).periscope is not None:
            b = (round(st.periscope_train / TURN_STEP_DEG) + step) * TURN_STEP_DEG % 360
            self._hand(f"vrid periskop {b:03d}")
            return
        pic = self._picture()
        if pic is None or not pic.objects:
            return
        objs = ordered_objects(pic)
        i = (self._index(pic) + step) % len(objs)
        self.selected_key = object_key(objs[i])
        self.draw_now()

    def _picture(self):
        game = getattr(self.app, "game", None)
        if game is None:
            return None
        if self._bridge_live(game):
            return game.knowledge.bridge
        return game.knowledge.periscope

    @staticmethod
    def _bridge_live(game) -> bool:
        """Kikaren utan att någon håller den: bryggans bild är den levande."""
        st = game.status()
        return st.periscope is None and st.bridge == "manned" and game.knowledge.bridge is not None

    def _share_look(self, bearing: float | None) -> None:
        if bearing is not None and hasattr(self.app, "look_bearing"):
            self.app.look_bearing = bearing

    def _index(self, pic) -> int:
        """Behåll valet mellan svepen om föremålet finns kvar, annars det närmaste fartyget."""
        objs = ordered_objects(pic)
        if self._pic_t != pic.t:
            self._pic_t = pic.t
            fresh = {object_key(o) for o in objs if not (0 <= o.seen_t < pic.t)}
            if self.selected_key not in fresh:
                self.selected_key = None        # nytt svep: välj bland det vi just såg
        look = getattr(self.app, "look_bearing", None)
        if self.selected_key is None and look is not None and objs:
            near = min(range(len(objs)), key=lambda i: abs(angle_diff(objs[i].bearing, look)))
            if abs(angle_diff(objs[near].bearing, look)) <= 60:    # det bryggan tittade på
                self.selected_key = object_key(objs[near])
        for i, o in enumerate(objs):
            if object_key(o) == self.selected_key:
                return i
        i = default_index(pic)
        if objs:
            self.selected_key = object_key(objs[i])
        return i

    def draw(self, body: Static, head: Static) -> None:
        game = getattr(self.app, "game", None)
        if game is None:
            return
        w, h = body.size.width, body.size.height
        if w < 30 or h < 8:
            return
        st = game.status()
        bridge_live = self._bridge_live(game)
        pic = game.knowledge.bridge if bridge_live else game.knowledge.periscope
        aim = st.periscope_train if st.periscope is not None else None
        age = 0 if pic is None else game.now - pic.t
        index = None if pic is None or aim is not None else self._index(pic)
        if aim is not None:
            self._share_look(aim)
        elif index is not None and pic.objects:
            self._share_look(ordered_objects(pic)[index].bearing)
        power = None if bridge_live or st.periscope_optic == "kikare" else (
            st.periscope_power if aim is not None else None)
        body.update(Text("\n").join(render_periscope(pic, w, h, index, age, game.clock_str, aim,
                                                      power)))
        note = None
        blocked = game.knowledge.periscope_blocked
        if blocked is not None and (pic is None or blocked[0] > pic.t):
            note = f"Is ovanför kl {game.clock_str(blocked[0])[:5]}, masten kom inte upp."
        up = None if aim is None else (st.periscope, st.periscope_up_s, aim)
        kikare = bridge_live or (aim is not None and st.periscope_optic == "kikare")
        t = header(pic, game.clock_str(pic.t) if pic else "", age, note, up,
                   "KIKARE, bryggan" if kikare else "PERISKOP", power)
        t.append("\n")
        if aim is not None:
            t.append(" ←/→ vrid · mellanslag förut · +/− förstoring (hålls uppe) · ↓ periskop ned"
                     " · Tab översikten · Esc tillbaka", style="dim")
        elif bridge_live:
            t.append(" ←/→ byt föremål · ↑ panoramat · Tab översikten · Esc tillbaka", style="dim")
        else:
            t.append(" ←/→ byt föremål · ↑ periskop upp · periskop ger ett svep, periskop 047 "
                     "eller S-3 en kort titt · Tab översikten · Esc tillbaka", style="dim")
        head.update(t)

