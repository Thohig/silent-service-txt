"""Arkitekturens gränser i importerna: kunskapen läser aldrig sanningen, och `sim/`
importerar aldrig Textual (designprinciperna 3 och 4 i CLAUDE.md)."""
import ast
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / "sim"

# Kunskapen: byggs bara av händelser på bussen.
KNOWLEDGE = ("knowledge", "tma", "zigzag", "icemap", "periscope", "chart", "profile", "sonar_view",
             "systems", "reports", "events")

# Sanningen och det som håller den (bara sensorer och stationer får läsa dem).
TRUTH = {"world", "entities", "ownship", "enemy", "weapons", "ice", "acoustics", "traffic",
         "convoy", "air", "harbor", "arctic", "exercise", "sonar", "ship", "game", "scenario"}


def _runtime_nodes(tree: ast.AST):
    """Alla noder utom de i `if TYPE_CHECKING:` (bara för typannotationer, laddas aldrig)."""
    todo = [tree]
    while todo:
        node = todo.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If) and isinstance(child.test, ast.Name) \
                    and child.test.id == "TYPE_CHECKING":
                todo.extend(child.orelse)
                continue
            todo.append(child)


def _file(mod: str) -> Path | None:
    """Modulens fil: `x.py` eller paketets `x/__init__.py`."""
    base = SIM / mod.replace(".", "/")
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.exists():
            return path
    return None


def _sim_imports(mod: str) -> set[str]:
    """Moduler i `sim/` som `mod` importerar när koden körs (relativt eller som `sim.x`),
    även inuti funktioner."""
    path = _file(mod)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pkg = mod.split(".") if path.name == "__init__.py" else mod.split(".")[:-1]
    out = set()
    for node in _runtime_nodes(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[:len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                parts = base + (node.module.split(".") if node.module else [])
            elif node.module and node.module.startswith("sim."):
                parts = node.module.split(".")[1:]
            else:
                continue
            if node.module is None:            # from . import x
                cands = [".".join(parts + [a.name]) for a in node.names]
            else:
                cands = [".".join(parts)]
            out.update(c for c in cands if _file(c) is not None)
        elif isinstance(node, ast.Import):
            out.update(a.name[4:] for a in node.names if a.name.startswith("sim."))
    return out


def _closure(mod: str) -> dict[str, str]:
    """Alla moduler `mod` når, med en modul som importerar dem (för felmeddelandet)."""
    seen, todo = {mod: ""}, [mod]
    while todo:
        m = todo.pop()
        for d in _sim_imports(m):
            if d not in seen:
                seen[d] = m
                todo.append(d)
    return seen


def test_knowledge_modules_never_reach_the_truth():
    for mod in KNOWLEDGE:
        reach = _closure(mod)
        bad = {m: via for m, via in reach.items() if m.split(".")[0] in TRUTH}
        assert not bad, f"{mod} når sanningen: " + ", ".join(
            f"{m} (via {via})" for m, via in sorted(bad.items()))


def test_sim_never_imports_textual():
    for path in SIM.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else []
            assert not any(n.split(".")[0] == "textual" for n in names), path


def test_the_guard_sees_a_forbidden_import():
    """Vakten själv: världen når sina sanningsmoduler, och typimporter räknas inte."""
    assert {"entities", "ownship", "goals"} <= set(_closure("world"))
    assert "world" not in _sim_imports("seabed")          # bara under TYPE_CHECKING
    assert "scenario.common" in _sim_imports("scenario")  # paket räknas
    assert "world" in _closure("scenario")


# --- stationernas väg till sanningen (sim/stations/base.py) -------------------------
STATIONS = SIM / "stations"


def _world_reads(path: Path) -> tuple[list[int], list[int]]:
    """Rader med `<x>.game.world` och med `<x>.world` (self, nav, station) i en fil."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    game_world, own_world = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "world":
            v = node.value
            if isinstance(v, ast.Attribute) and v.attr == "game":
                game_world.append(node.lineno)
            elif isinstance(v, ast.Name) and v.id in ("self", "nav", "station"):
                own_world.append(node.lineno)
    return game_world, own_world


def test_stations_reach_the_world_only_through_base():
    """Bara base.py läser game.world; self.world bara i stationer som är sensorer eller vapen
    (REACHES_WORLD = True i modulen, eller i paketets station.py)."""
    for path in STATIONS.rglob("*.py"):
        if path.name == "base.py":
            continue
        game_world, own_world = _world_reads(path)
        assert not game_world, f"{path.relative_to(SIM)} läser game.world på rad {game_world}"
        if own_world:
            home = path.parent / "station.py" if path.parent != STATIONS else path
            assert "REACHES_WORLD = True" in home.read_text(encoding="utf-8"), \
                f"{path.relative_to(SIM)} når världen (rad {own_world}) utan REACHES_WORLD"


def test_the_world_guard_sees_a_station_that_reads_the_world(tmp_path):
    bad = tmp_path / "x.py"
    bad.write_text("class X:\n    def f(self):\n        return self.game.world.contacts\n")
    assert _world_reads(bad) == ([3], [])
