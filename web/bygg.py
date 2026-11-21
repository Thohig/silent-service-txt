"""Bygg webbversionen till en mapp som kan läggas på GitHub Pages (eller provas lokalt).

    uv run python web/bygg.py [mål]          # standard web/dist
    python -m http.server -d web/dist 8000   # prova på http://localhost:8000

Mappen får `index.html`, ikonen och `k114.zip` (sim/, ui/ och startfilerna). Pyodide,
numpy, Textual och xterm.js hämtas av webbläsaren från CDN och PyPI.
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PACKAGES = ("sim", "ui")
START = ("start.py", "pyodide_driver.py", "web_audio.py")


def build(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out / "k114.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for pkg in PACKAGES:
            for f in sorted((ROOT / pkg).rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                    z.write(f, f.relative_to(ROOT).as_posix())
        for name in START:
            z.write(WEB / name, name)
    shutil.copy(WEB / "index.html", out / "index.html")
    shutil.copy(ROOT / "ikon" / "k114-1024.png", out / "k114.png")
    (out / ".nojekyll").touch()
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else WEB / "dist"))
