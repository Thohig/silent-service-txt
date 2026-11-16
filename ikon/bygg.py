"""Bygger K-114.icns och png-filer ur k114.svg (macOS).

    uv run --with pillow ikon/bygg.py

Quick Look (qlmanage) rastrerar svg-filen på vit botten; hörnen görs
genomskinliga med en mask efter samma rundade ruta som i svg-filen.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SVG = HERE / "k114.svg"
BOX = (100, 100, 924, 924)   # samma ruta som i k114.svg
RADIUS = 185
SIZES = [16, 32, 64, 128, 256, 512, 1024]


def render(size: int = 1024) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["qlmanage", "-t", "-s", str(size), "-o", tmp, str(SVG)],
                       check=True, capture_output=True)
        image = Image.open(Path(tmp) / f"{SVG.name}.png").convert("RGBA")
        image.load()
    big = 4
    mask = Image.new("L", (size * big, size * big), 0)
    scale = size * big / 1024
    ImageDraw.Draw(mask).rounded_rectangle(
        [c * scale for c in BOX], radius=RADIUS * scale, fill=255)
    image.putalpha(mask.resize((size, size), Image.LANCZOS))
    return image


def main() -> None:
    master = render()
    master.save(HERE / "k114-1024.png")
    master.resize((256, 256), Image.LANCZOS).save(HERE / "k114-256.png")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "K-114.iconset"
        iconset.mkdir()
        for s in SIZES[:-1]:
            master.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
            master.resize((2 * s, 2 * s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset),
                        "-o", str(HERE / "K-114.icns")], check=True)
    print("klart:", ", ".join(p.name for p in sorted(HERE.glob("*.png")) + [HERE / "K-114.icns"]))


if __name__ == "__main__":
    if not shutil.which("qlmanage"):
        raise SystemExit("qlmanage saknas – skriptet kräver macOS")
    main()
