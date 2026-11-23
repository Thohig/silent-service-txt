"""Första skillnaden: samma scenario och frö med arbetskopian och en äldre version (en commit).

Spelar båda (`spela.py`, ja-boten eller den passiva), jämför rapportflödena och skriver ut den
första rapport som skiljer, med rapporterna före och efter från båda, och utfallen. Den äldre
versionen packas ut med `git archive` i logs/skillnad/<commit>/ (arbetskatalogen rörs inte).

Användning (från repots rot):
    uv run python kalibrering/skillnad.py scenario frö [--mot COMMIT] [--bot ja|passiv]
                                          [--minuter N] [--sammanhang N]
Standard: mot HEAD, ja-boten, hela spelet, 12 rader sammanhang. Avslutar med 1 om flödena skiljer.
T.ex.: skillnad.py clyde 15 --mot 09baead
"""
import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(ROOT))
import json
import os
import subprocess
import sys
import tarfile
import io
from concurrent.futures import ThreadPoolExecutor

SPELA = _Path(__file__).with_name("spela.py")


def unpack(ref: str) -> _Path:
    """Den äldre versionen utpackad (en gång per commit)."""
    sha = subprocess.run(["git", "rev-parse", "--short", ref], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.strip()
    dest = ROOT / "logs" / "skillnad" / sha
    if not (dest / "sim").exists():
        dest.mkdir(parents=True, exist_ok=True)
        data = subprocess.run(["git", "archive", sha, "sim"], cwd=ROOT, capture_output=True,
                              check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter="data")
    return dest


def stream(root: _Path, key: str, seed: int, bot: str, minutes: int) -> list[dict]:
    env = dict(os.environ, PYTHONHASHSEED="0")
    out = subprocess.run([sys.executable, str(SPELA), str(root), key, str(seed), bot, str(minutes)],
                         capture_output=True, text=True, env=env, check=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def key_of(r: dict) -> tuple:
    return (r.get("t"), r.get("typ"), r.get("text"))


def show(rows: list[dict], i: int, n: int, label: str) -> None:
    print(f"--- {label}")
    for j in range(max(0, i - n), min(len(rows), i + n + 1)):
        r = rows[j]
        mark = ">>" if j == i else "  "
        if "utfall" in r:
            print(f"{mark} UTFALL {r['utfall']} ({r['t'] // 60} min)")
        else:
            print(f"{mark} {r['klocka']} {r['typ']}: {r['text'][:170]}")


def main() -> int:
    a = sys.argv[1:]
    def opt(name, default):
        return a[a.index(name) + 1] if name in a else default
    key, seed = a[0], int(a[1])
    ref, bot = opt("--mot", "HEAD"), opt("--bot", "ja")
    minutes, ctx = int(opt("--minuter", 15 * 60)), int(opt("--sammanhang", 12))
    old_root = unpack(ref)
    with ThreadPoolExecutor(2) as ex:
        f_new = ex.submit(stream, ROOT, key, seed, bot, minutes)
        f_old = ex.submit(stream, old_root, key, seed, bot, minutes)
        new, old = f_new.result(), f_old.result()
    i = next((j for j, (x, y) in enumerate(zip(old, new)) if key_of(x) != key_of(y)),
             None if len(old) == len(new) else min(len(old), len(new)))
    print(f"{key} frö {seed}, {bot}-boten: {ref} {old[-1].get('utfall')} ({old[-1]['t'] // 60} min), "
          f"arbetskopian {new[-1].get('utfall')} ({new[-1]['t'] // 60} min)")
    if i is None:
        print("samma rapportflöde")
        return 0
    print(f"första skillnaden vid rapport {i}:")
    show(old, i, ctx, ref)
    show(new, i, ctx, "arbetskopian")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
