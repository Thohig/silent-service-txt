"""Frasbok: gör strukturerade rapporter till muntlig svenska.

Varje meddelandetyp har en funktion data -> text. Rendering sker vid
leverans, efter rapportfiltren, så att ändrad data (trötthet, sabotage)
alltid formuleras korrekt. Framtida röster och personligheter kan byta
ut eller variera fraserna här utan att stationerna ändras.
"""
from __future__ import annotations

from typing import Any, Callable

from .fmt import fmt_course, kn, nm
from .geo import angle_diff
from .reports import Quality, Report

Data = dict[str, Any]
Phrase = Callable[[Data], str]


# --- hjälp ------------------------------------------------------------------
def solution_sentence(sol: Data) -> str:
    """Plottlagets lösning i ord. Säger inte mer än datan bär."""
    q = Quality(sol["quality"])
    if q >= Quality.GOD:
        rng = f"avstånd {nm(sol['range_nm'])} sjömil"
    else:
        lo = max(0.2, sol["range_nm"] - 1.5 * sol["range_sigma"])
        hi = sol["range_nm"] + 1.5 * sol["range_sigma"]
        rng = f"avstånd cirka {nm(sol['range_nm'])} sjömil, någonstans mellan {nm(lo)} och {nm(hi)}"
    if sol["course_sigma"] > 40 or sol["speed_sigma"] > 8:
        motion = "kurs och fart kan vi inte säga ännu"
    elif q >= Quality.GOD:
        motion = f"kurs {fmt_course(sol['course'])}, fart {kn(round(sol['speed']))} knop"
    else:
        motion = (f"kurs cirka {fmt_course(round(sol['course'] / 5) * 5)}, "
                  f"fart cirka {kn(round(sol['speed']))} knop")
    return f"bäring {fmt_course(sol['bearing'])}, {rng}, {motion}."


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _basis(sol: Data) -> str:
    return f"({sol['n_obs']} bäringar under {sol['span_s'] // 60} min.)"














# --- plott ----------------------------------------------------------------------
def _improved(d: Data) -> str:
    sol = d["solution"]
    return (f"Kapten, plottet. Lösningen på {d['designation']} är nu "
            f"{Quality(sol['quality']).label}. {_cap(solution_sentence(sol))}")


def _suggest(d: Data) -> str:
    q = Quality(d["quality"]).label
    if d["first"]:
        return (f"Kapten, plottet. Lösningen på {d['designation']} är {q}, på rak kurs "
                f"får vi inget avstånd. Föreslår kursändring till {fmt_course(d['course'])}.")
    return (f"Kapten, plottet. Lösningen på {d['designation']} är fortfarande {q}. "
            f"Ett nytt ben skulle hjälpa. Föreslår kurs {fmt_course(d['course'])}.")


def _solution(d: Data) -> str:
    sol = d["solution"]
    if Quality(sol["quality"]) == Quality.DALIG:
        need = {"turn": " Vi behöver ett kursbyte för att få avstånd.",
                "time": " Vi behöver mer tid på det här benet."}.get(d.get("need"), "")
        return (f"{d['designation']}: lösningen är dålig. Bästa gissning: "
                f"{solution_sentence(sol)}{need} {_basis(sol)}")
    return (f"{d['designation']}: {_cap(solution_sentence(sol))} "
            f"Kvalitet {Quality(sol['quality']).label}. {_basis(sol)}")


def _table_summary(d: Data) -> str:
    sol = d.get("solution")
    if sol is None:
        return f"{d['designation']}: {d['n']} bäringar, ingen lösning ännu."
    return (f"{d['designation']}: {d['n']} bäringar. Uppskattning: {solution_sentence(sol)} "
            f"Kvalitet {Quality(sol['quality']).label}, avvikelse {nm(sol['rms_residual'])}° rms.")


PHRASES: dict[str, Phrase] = {
    # allmänt
    "order.unknown": lambda d: f"Kapten, {d['reason']}." if d.get("reason") else "Kapten?",
    "system.help": lambda d: d["text"],
    "order.executing": lambda d: f"Verkställer: {d['what']}.",
    "order.no_suggestion": lambda d: "Det finns inget förslag att verkställa, kapten.",
    "order.declined": lambda d: "Uppfattat, vi avvaktar.",
    "order.suggestion_repeat": lambda d: f"Senaste förslaget: {d['text']}",
    "system.text": lambda d: d["text"],
    # plott
    "plot.improved": _improved,
    "plot.suggest": _suggest,
    "plot.solution": _solution,
    "plot.maneuver": lambda d: f"Kapten, plottet! {d['designation']} har troligen ändrat kurs eller "
    f"fart, bäringarna stämmer inte längre. Vi börjar om lösningen.",
    "plot.few_bearings": lambda d: f"För få bäringar på {d['designation']} ännu, kapten.",
    "plot.no_contacts": lambda d: "Vi har inga kontakter, kapten.",
    "plot.which": lambda d: "Vilken kontakt, kapten? " + ", ".join(d["options"]) + ".",
    "plot.unknown_contact": lambda d: f"Ingen kontakt betecknad {d['designation']}, kapten.",
    "plot.no_bearings": lambda d: f"Inga bäringar loggade på {d['designation']}.",
    "plot.table": _table_summary,
}


def register(phrases: dict[str, Phrase]) -> None:
    """Stationer registrerar sina egna fraser."""
    PHRASES.update(phrases)


def _plot_rows(d: Data, clock: Callable[[int], str]) -> list[list[str]]:
    rows = []
    for r in d["rows"]:
        row = [clock(r["t"]), fmt_course(r["bearing"]), fmt_course(r["own_course"])]
        if r.get("predicted") is not None:
            dev = angle_diff(r["bearing"], r["predicted"])
            row += [fmt_course(r["predicted"]), f"{dev:+.1f}°".replace(".", ",")]
        else:
            row += ["–", "–"]
        rows.append(row)
    return rows


def render(report: Report, clock: Callable[[int], str]) -> Report:
    """Fyll i text (och tabell) från rapportens typ och data."""
    phrase = PHRASES.get(report.type)
    report.text = phrase(report.data) if phrase else f"[{report.type}] {report.data}"
    if report.data.get("order"):
        report.text += f" [ja: {report.data['order']}]"
    if report.type == "plot.table":
        report.table = _plot_rows(report.data, clock)
        report.table_header = ["Tid", "Bäring", "Egen kurs", "Lösning", "Avvikelse"]
    return report
