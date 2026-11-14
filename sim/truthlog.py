"""Loggar sanningen till fil för felsökning. Aldrig synlig i spelet."""
from __future__ import annotations

from pathlib import Path
from typing import TextIO

from .world import World


class TruthLog:
    def __init__(self, path: Path | str, every: int = 10):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f: TextIO = self.path.open("w", encoding="utf-8")
        self.every = every

    def tick(self, world: World) -> None:
        if world.time % self.every:
            return
        o = world.own.state
        sy = world.own.sys
        parts = [f"t={world.time:6d} OWN x={o.x:6.2f} y={o.y:6.2f} "
                 f"k={o.course:5.1f} v={o.speed:4.1f} d={o.depth:5.1f} "
                 f"rx={sy.reactor} prop={sy.propulsion} bat={sy.battery:.2f} "
                 f"hull={sy.hull:.2f} flood={sy.flooding:.1f}"]
        for v in world.contacts:
            if v.sunk and v.kind != "destroyer":
                continue
            s = v.state
            parts.append(
                f"{v.id}{'(sänkt)' if v.sunk else ''} x={s.x:6.2f} y={s.y:6.2f} "
                f"k={s.course:5.1f} v={s.speed:4.1f} r={world.true_range(v):5.2f} "
                f"b={world.true_bearing(v):5.1f} SE={world.raw_signal_excess(v):+5.1f}")
        for ai in world.ais:
            d = ai.datum
            parts.append(f"AI {ai.vessel.id} {ai.state}/{ai.roe}" +
                         (f" datum=({d.x:.2f},{d.y:.2f},{d.depth:.0f}m ±{d.sigma:.2f})" if d else ""))
        self.write(" | ".join(parts))

    def note(self, t: int, text: str) -> None:
        self.write(f"t={t:6d} >> {text}")

    def write(self, line: str) -> None:
        self._f.write(line + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()
