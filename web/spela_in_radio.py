"""Spela in Radio Moskvas sändningar med Milena till `ui/radio/` (görs på en Mac, sedan committas).

    uv run python web/spela_in_radio.py

Webbläsarens talsyntes går förbi mixern, så rösten kan inte gå genom radion där; inspelningen
kan (`ui.menu_audio.recorded`). Kör om när `BULLETINS` (`ui/menutext.py`) ändras:
`tests/test_menu_audio.py` säger till när en sändning saknar inspelning. Gamla inspelningar
som ingen sändning använder tas bort.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.menu_audio import (RADIO_RATE_WPM, RECORDING_RATE, RECORDINGS,  # noqa: E402
                           recording_path)
from ui.menutext import BULLETINS  # noqa: E402
from ui.voices import MacSay  # noqa: E402


def write_wav(path: Path, x: np.ndarray, rate: int) -> None:
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def main() -> int:
    say = MacSay()
    voice = say.voice("ru")
    if voice is None:
        print("Milena saknas (Systeminställningar › Hjälpmedel › Uppläst innehåll › Röster).")
        return 1
    RECORDINGS.mkdir(exist_ok=True)
    keep = set()
    for b in BULLETINS:
        path = recording_path(b.ru)
        keep.add(path.name)
        x = say.render(b.ru, voice, RADIO_RATE_WPM, RECORDING_RATE)
        if x is None or not len(x):
            print(f"kunde inte läsa: {b.ru}")
            return 1
        write_wav(path, x, RECORDING_RATE)
        print(f"{path.name}  {len(x) / RECORDING_RATE:4.1f} s  {b.sv}")
    for old in RECORDINGS.glob("*.wav"):
        if old.name not in keep:
            old.unlink()
            print(f"borttagen: {old.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
