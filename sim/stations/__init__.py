"""Besättningsstationer. Lägg till nya system här."""
from .base import Station
from .navigation import NavigationStation, SetCourse, SetDepth, SetSpeed
from .plot import PlotTeam, QuerySolution, ShowPlot
from .sonar_room import SonarRoom

# Ordningen är uppdateringsordningen varje tick:
# navigation först (egen rörelse), sedan sensorer, sedan analys.
DEFAULT_STATIONS: list[type[Station]] = [NavigationStation, SonarRoom, PlotTeam]

__all__ = [
    "Station", "DEFAULT_STATIONS",
    "NavigationStation", "SetCourse", "SetSpeed", "SetDepth",
    "SonarRoom", "PlotTeam", "QuerySolution", "ShowPlot",
]
