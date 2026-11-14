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
        parts = [f"t={world.time:6d} OWN x={o.x:6.2f} y={o.y:6.2f} "
                 f"k={o.course:5.1f} v={o.speed:4.1f} d={o.depth:5.1f}"]
        for v in world.contacts:
            s = v.state
            parts.append(
                f"{v.id} x={s.x:6.2f} y={s.y:6.2f} k={s.course:5.1f} v={s.speed:4.1f} "
                f"r={world.true_range(v):5.2f} b={world.true_bearing(v):5.1f} "
                f"SE={world.raw_signal_excess(v):+5.1f}")
        self.write(" | ".join(parts))

    def note(self, t: int, text: str) -> None:
        self.write(f"t={t:6d} >> {text}")

    def write(self, line: str) -> None:
        self._f.write(line + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()
