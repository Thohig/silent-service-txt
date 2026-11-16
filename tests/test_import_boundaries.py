"""Arkitekturens gränser i importerna: kunskapen läser aldrig sanningen, och `sim/`
importerar aldrig Textual (designprinciperna 3 och 4 i CLAUDE.md)."""
import ast
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / "sim"

# Kunskapen: byggs bara av händelser på bussen.
KNOWLEDGE = ("knowledge", "tma", "zigzag", "icemap", "periscope", "chart", "profile",
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


def _sim_imports(mod: str) -> set[str]:
    """Moduler i `sim/` som `mod` importerar när koden körs (relativt eller som `sim.x`),
    även inuti funktioner."""
    path = SIM / (mod.replace(".", "/") + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pkg = mod.split(".")[:-1]
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
            out.update(c for c in cands if (SIM / (c.replace(".", "/") + ".py")).exists())
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
        bad = {m: via for m, via in reach.items() if m in TRUTH}
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
