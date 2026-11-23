"""Inspelningen: sonarrummet spelar in en Polarisbåt på band (Clyde).

Del av SonarRoom (sonar_room.py). Bara när ordern kräver en inspelning ("inspelning" i
`Knowledge.order_tasks`). Bandspelaren går när en kontakt klassad som Polarisbåt hörs med gott
ljud (`RECORD_SE` över tröskeln, ur sonarens egna bäringar); efter `RECORD_S` sekunder med gott
ljud är inspelningen klar. Sonar säger när bandet börjar gå, halvvägs, när ljudet blir för svagt
och när det är klart. Den klara inspelningen antecknas i `World.mission["recorded"]` (sanningens
id, för uppdragsmålet `RecordGoal`); rapporterna nämner bara beteckningen.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..fmt import minutes
from .. import phrases
from .. import russian as R
from ..events import RecordingMade
from ..geo import angle_diff, norm360

RECORD_SE = 8.0            # dB över tröskeln: gott nog för bandet
RECORD_S = 600             # så länge med gott ljud för en användbar inspelning
RECORD_STEP_S = 5
RECORD_FRESH_S = 12        # en bäring så här gammal räknas
WEAK_AFTER_S = 60          # utan gott ljud så länge (med något på bandet): säg det
WEAK_REPEAT_S = 300
HELD_BEFORE_SUGGEST_S = 60  # kontakten hållen så länge innan sonar föreslår att gå mot den
LISTEN_DEPTH_M = 40         # över skiktet
CLOSE_SPEED_KN = 5          # smygmotorns bästa
RECORD_CLASS = "Polaris"
BAFFLE_MARGIN_DEG = 10.0    # ... och så här långt utanför döda sektorn räknas som akterut


@dataclass
class _Tape:
    seconds: int = 0
    last_good: int = -10**9
    half_said: bool = False
    weak_said: int = -10**9
    done: bool = False


PHRASES = {
    "sonar.record.start": lambda d: f"Kapten, sonar. Bandspelaren går på {d['designation']}, "
    f"Polarisbåten. Vi behöver {d['minutes']} minuter med gott ljud.",
    "sonar.record.half": lambda d: f"Halva inspelningen av {d['designation']} på bandet, "
    f"{minutes(d['left'])} kvar.",
    "sonar.record.weak": lambda d: f"Kapten, sonar. {d['designation']} är för svag för bandet. "
    f"{minutes(d['minutes'])} av {d['need']} inspelade. Vi måste närmare, eller låta den komma till oss.",
    "sonar.suggest.record_up": lambda d: f"Kapten, sonar. Under skiktet hör vi {d['designation']} "
    f"för svagt för bandet. Föreslår djup {d['depth']}, över skiktet.",
    "sonar.suggest.record_close": lambda d: f"Kapten, sonar. {d['designation']} "
    + ("ligger akterut, där skymmer skrovet och skruven bandet. Sista bäringen" if d.get("astern")
       else "är för svag för bandet, bäring") + f" {d['bearing']:03d}. Föreslår kurs "
    f"{d['bearing']:03d} och fart {d['speed']} mot den.",
    "sonar.record.done": lambda d: f"Kapten, sonar! Inspelningen av {d['designation']} är klar: "
    f"{minutes(d['minutes'])} med gott ljud, skruven och maskinen hörs tydligt.",
}
phrases.register(PHRASES)

RU_PHRASES = {
    "sonar.record.start": lambda d: f"{R.CAPTAIN}, акустик. Магнитофон включён, "
    f"{R.contact(d['designation'])}.",
    "sonar.record.half": lambda d: f"Половина записи, осталось {R.count(d['left'], R.MINUTE)}.",
    "sonar.record.weak": lambda d: f"{R.CAPTAIN}, акустик. Сигнал слабый для записи.",
    "sonar.suggest.record_up": lambda d: f"{R.CAPTAIN}, акустик. Под слоем слышно слабо. "
    f"Предлагаю глубину {R.count(d['depth'], R.METER)}.",
    "sonar.suggest.record_close": lambda d: f"{R.CAPTAIN}, акустик. Сигнал слабый. Предлагаю курс "
    f"{R.course(d['bearing'])}, ход {R.count(d['speed'], R.KNOT)}.",
    "sonar.record.done": lambda d: f"{R.CAPTAIN}, акустик! Запись готова, "
    f"{R.count(d['minutes'], R.MINUTE)}.",
}
phrases.register_ru(RU_PHRASES)


class RecordingMixin:
    """Del av SonarRoom: bandspelaren."""

    def _recording_init(self) -> None:
        self._tapes: dict[str, _Tape] = {}

    def recorded_s(self, designation: str) -> int:
        t = self._tapes.get(designation)
        return t.seconds if t else 0

    def _recording_watch(self) -> None:
        k = self.game.knowledge
        if "inspelning" not in k.order_tasks or self.now % RECORD_STEP_S:
            return
        for tr in k.tracks.values():
            if not tr.held or RECORD_CLASS not in tr.classification:
                continue
            tape = self._tapes.setdefault(tr.designation, _Tape())
            if tape.done:
                continue
            obs = [o for o in tr.observations if o.source == "sonar" and
                   self.now - o.t <= RECORD_FRESH_S]
            good = bool(obs) and obs[-1].se >= RECORD_SE
            d = {"designation": tr.designation}
            if good:
                if tape.seconds == 0:
                    self.say("sonar.record.start", {**d, "minutes": RECORD_S // 60}, kind="contact")
                tape.seconds += RECORD_STEP_S
                tape.last_good = self.now
                if tape.seconds >= RECORD_S:
                    tape.done = True
                    self.say("sonar.record.done", {**d, "minutes": RECORD_S // 60}, kind="contact")
                    self._mark_recorded(tr.designation)
                    self.game.bus.publish(RecordingMade(self.now, tr.designation))
                elif not tape.half_said and tape.seconds >= RECORD_S // 2:
                    tape.half_said = True
                    self.say("sonar.record.half",
                             {**d, "left": round((RECORD_S - tape.seconds) / 60)}, kind="info")
                continue
            self._suggest_closer(tr, obs)
            if tape.seconds > 0 and self.now - tape.last_good >= WEAK_AFTER_S and \
                    self.now - tape.weak_said >= WEAK_REPEAT_S:
                tape.weak_said = self.now
                self.say("sonar.record.weak", {**d, "minutes": tape.seconds // 60,
                                               "need": RECORD_S // 60}, kind="info")

    def _suggest_closer(self, tr, obs) -> None:
        """För svagt för bandet: över skiktet om vi är under det, annars mot kontakten (mot sista bäringen
        när den ligger akterut i döda sektorn och vi inte har någon färsk)."""
        k = self.game.knowledge
        if self.now - tr.first_t < HELD_BEFORE_SUGGEST_S or k.hunted(self.now) or \
                k.torpedo_alarm(self.now):
            return
        st = self.own.state
        if not obs:
            # ingen färsk bäring: ligger den akterut i döda sektorn går vi mot sista bäringen
            b = tr.last_bearing
            if b is None or abs(angle_diff(b, norm360(st.course + 180.0))) > \
                    self.own.baffle_deg + BAFFLE_MARGIN_DEG:
                return
            b = round(b) % 360
            self.suggest("record_close", "sonar.suggest.record_close",
                         {"designation": tr.designation, "bearing": b, "speed": CLOSE_SPEED_KN,
                          "astern": True},
                         order=f"kurs {b:03d}, fart {CLOSE_SPEED_KN}", cooldown=300)
            return
        layer = self.layer_depth()
        d = {"designation": tr.designation}
        if layer is not None and st.ordered_depth >= layer:
            self.suggest("record_up", "sonar.suggest.record_up", {**d, "depth": LISTEN_DEPTH_M},
                         order=f"djup {LISTEN_DEPTH_M}", cooldown=600)
            return
        b = round(obs[-1].bearing) % 360
        self.suggest("record_close", "sonar.suggest.record_close",
                     {**d, "bearing": b, "speed": CLOSE_SPEED_KN},
                     order=f"kurs {b:03d}, fart {CLOSE_SPEED_KN}", cooldown=300)
