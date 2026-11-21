"""Mottagningen: sambandstillfällena på kortvåg och långvåg, stympade telegram, leveransen."""
from __future__ import annotations


from ...headquarters import MAX_PER_WINDOW
from ...events import (NuclearOrderRead, PositionReported, TasksOrdered,
                      TelegramReceived)
from ...ownship import ANTENNA_DEPTH
from .common import (
    RECEIVE_S, VLF_DEPTH, VLF_RECEIVE_S, VLF_SLOW_KN, VLF_SPEED, VLF_UP_DEPTH, garble,
)


class ReceptionMixin:
    """Mottagningen, som RadioStation ärver."""

    def _broadcast(self) -> None:
        """Radiomannen har hittat Moskva (eller bara bärvågen)."""
        self._listen_until = None
        if not self.broadcasts:
            return
        b = self.broadcasts[self._broadcast_n % len(self.broadcasts)]
        self._broadcast_n += 1
        self.received += 1
        self.game.bus.publish(TelegramReceived(self.now, b.sv, "broadcast", self.received))
        strip = {"text": b.sv, "telegram": self.received, "telegram_kind": "broadcast"}
        if b.ru:
            self.say("radio.moscow", {**strip, "ru": b.ru, "read_aloud": b.sv}, kind="info")
        else:
            self.say("radio.moscow.silent", strip, kind="info")

    def _receive(self, i: int) -> None:
        """Sambandstillfället är öppet: masten på antenndjup, annars flytkabeln på långvåg."""
        st = self.own.state
        working = self.own.sys.health["radio"] >= 0.3
        if st.depth <= VLF_DEPTH and not self.masts_free:
            self.cable = False
            if i not in self._ice_warned:
                self._ice_warned.add(i)
                self.say("radio.ice")
        elif st.depth <= ANTENNA_DEPTH and working:
            self.cable = False
            self._listen += 1
            if self._listen >= RECEIVE_S:
                self._handled.add(i)
                self._deliver(upto=i)
        elif st.depth <= VLF_DEPTH and working:
            if not self.cable:
                self.cable = True
                if i not in self._cable_said:
                    self._cable_said.add(i)
                    self.say("radio.cable.out", {"minutes": VLF_RECEIVE_S // 60})
            if st.speed > VLF_SPEED + 0.1:
                if i not in self._cable_fast:
                    self._cable_fast.add(i)
                    self.suggest(f"cable_fast{i}", "radio.cable.fast", {}, order=f"fart {VLF_SLOW_KN}",
                                 cooldown=120)
                return
            self._vlf += 1
            if self._vlf >= VLF_RECEIVE_S:
                why = self._vlf_quality()
                pending = self._pending_texts(upto=i)
                if not why or not pending:
                    self._handled.add(i)
                    self.cable = False
                    self._deliver(upto=i, via="vlf")
                else:
                    self._vlf = 0               # stympat: lyssna på omsändningen
                    if i not in self._garbled:
                        self._garbled.add(i)
                        self._say_garbled(pending[0], why)
        else:
            self.cable = False

    def _vlf_quality(self) -> list[str]:
        """Varför långvågen kommer in stympad (tom: hel). Mörkret, låg fart (kabeln flyter
        i ytan) och litet djup (kabeln räcker) ger var sitt plus; två räcker."""
        st = self.own.state
        night = not self.world.env.is_day(self.now)
        ok = {"day": night, "speed": st.speed <= VLF_SLOW_KN + 0.1,
              "depth": st.depth <= VLF_UP_DEPTH + 0.5}
        if sum(ok.values()) >= 2:
            return []
        return [k for k, v in ok.items() if not v]

    def _pending_texts(self, upto: int) -> list[str]:
        """Det staben sänder vid detta tillfälle: scenariots radiogram och stabens svar."""
        out = [m.text for m in self.messages[self._next_msg:upto + 1]]
        if self.theatre is not None:
            out += [m.text for m in self.theatre.pending(self.world)]
        return out + self.hq.queue[:MAX_PER_WINDOW]

    def _say_garbled(self, text: str, why: list[str]) -> None:
        st = self.own.state
        parts = ([f"djup {VLF_UP_DEPTH}"] if "depth" in why and st.ordered_depth > VLF_UP_DEPTH else []) \
            + ([f"fart {VLF_SLOW_KN}"] if "speed" in why and st.ordered_speed > VLF_SLOW_KN else [])
        what = " och ".join(parts) or None
        d = {"why": why, "what": what, "telegram": "?", "telegram_kind": "telegram",
             "text": garble(text, self.game.rng_for("radio"))}
        if what:
            self.suggest("garbled", "radio.garbled", d, order=what, cooldown=300)
        else:
            self.say("radio.garbled", d)

    def _deliver(self, upto: int, via: str = "mast") -> None:
        msgs = []
        while self._next_msg <= upto and self._next_msg < len(self.messages):
            msgs.append(self.messages[self._next_msg])
            self._next_msg += 1
        if self.theatre is not None:            # krigsskådeplatsens uppgifter (theatre.py)
            msgs += self.theatre.deliver(self.world)
        # staben skriver sina svar med det nya i telegrammen för ögonen (krig, ny uppgift,
        # hemkallelse), och svaren på det vi sänt kommer före de nya orderna
        for msg in msgs:
            self.hq.read_order(msg.flags)
        replies = self.hq.outgoing()             # stabens svar på det vi sänt (eller inte sänt)
        for text in replies:
            self._telegram(text, via)
        for msg in msgs:
            self._radiogram(msg, via)
        if not msgs and not replies:
            self.say("radio.nothing")

    def _radiogram(self, msg, via: str) -> None:
        """Ett radiogram från staben (`radiogram.RadioMessage`): texten och det flaggorna säger."""
        self._telegram(msg.text, via)
        if "nuclear" in msg.flags or "war" in msg.flags:
            self.game.bus.publish(NuclearOrderRead(self.now, msg.flags.get("nuclear"),
                                                   msg.flags.get("war"),
                                                   f"telegram {self.received}"))
        self.world.mission.update(msg.flags)
        if "tasks" in msg.flags:
            self.game.bus.publish(TasksOrdered(self.now, tuple(msg.flags["tasks"]),
                                               f"telegram {self.received}"))
        if msg.flags.get("report_requested"):
            self.hq.request_report()
        elif "tasks" in msg.flags:          # en ny uppgift utan rapport: staben väntar inte på någon
            self.hq.cancel_report_request()
        if msg.waypoint is not None:
            name, x, y, sigma, t_pos = msg.waypoint
            self.game.bus.publish(PositionReported(self.now, name, x, y, sigma, t_pos,
                                                   motion=msg.motion, task="tasks" in msg.flags))

    def _telegram(self, text: str, via: str = "mast") -> None:
        self.delivered.append(text)
        self.received += 1
        self.game.bus.publish(TelegramReceived(self.now, text, "telegram", self.received))
        self.say("radio.message", {"text": text, "telegram": self.received, "via": via,
                                   "telegram_kind": "telegram", "read_aloud": text},
                 kind="info", alarm=True)
