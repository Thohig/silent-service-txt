"""Statusrad och rapportlogg."""
from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.widgets import RichLog, Static

from sim.fmt import kn
from sim.game import StatusSnapshot
from sim.geo import fmt_course
from sim.reports import Quality, Report

QUALITY_STYLE = {
    Quality.DALIG: "bold red",
    Quality.OSAKER: "yellow",
    Quality.GOD: "green",
    Quality.SAKER: "bold bright_green",
}

ROLE_STYLE = {
    "sonar": "bold cyan",
    "navigator": "bold green",
    "plot": "bold magenta",
    "captain": "bold white",
}


def _clock(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class StatusBar(Static):
    def show(self, s: StatusSnapshot) -> None:
        t = Text()

        def field(label: str, value: str, target: str | None, unit: str = "") -> None:
            t.append(f" {label} ", style="dim")
            if target is None:
                t.append(f"{value}{unit}", style="bold")
            else:
                t.append(value, style="bold yellow")
                t.append(f" ▸{target}{unit}", style="yellow")
            t.append("  │")

        field("DJUP", f"{s.depth:.0f}",
              f"{s.ordered_depth:.0f}" if "depth" in s.changing else None, " m")
        field("KURS", fmt_course(s.course),
              fmt_course(s.ordered_course) if "course" in s.changing else None)
        field("FART", f"{s.speed:.1f}".replace(".", ","),
              kn(s.ordered_speed) if "speed" in s.changing else None, " kn")
        t.append(" TID ", style="dim")
        t.append(_clock(s.clock), style="bold")
        t.append("  │")
        t.append(" ×", style="dim")
        t.append(f"{s.time_scale}", style="bold red" if s.time_scale > 1 else "bold")
        if s.contacts_held:
            t.append("  │ ", style="")
            t.append("KONTAKT ", style="dim")
            t.append(" ".join(s.contacts_held), style="bold cyan")
        self.update(t)


class ReportLog(RichLog):
    def add_report(self, clock: str, r: Report) -> None:
        line = Text()
        line.append(f"{clock} ", style="dim")
        if r.kind == "system":
            line.append(r.text, style="dim italic")
            self.write(line)
            return
        if r.alarm:
            line.append("▲ ", style="bold red")
        line.append(f"{r.speaker}: ", style=ROLE_STYLE.get(r.role, "bold"))
        line.append(r.text, style="bold" if r.alarm else "")
        if r.quality is not None:
            line.append(f"  [{r.quality.label}]", style=QUALITY_STYLE[r.quality])
        self.write(line)
        if r.table:
            table = Table(*(r.table_header or []), box=None, padding=(0, 2),
                          header_style="dim", show_edge=False)
            for row in r.table:
                table.add_row(*row)
            self.write(table)

    def add_captain(self, clock: str, text: str) -> None:
        line = Text()
        line.append(f"{clock} ", style="dim")
        line.append("Kapten: ", style=ROLE_STYLE["captain"])
        line.append(text, style="italic")
        self.write(line)

    def add_system(self, clock: str, text: str, style: str = "dim italic") -> None:
        line = Text()
        line.append(f"{clock} ", style="dim")
        line.append(text, style=style)
        self.write(line)
