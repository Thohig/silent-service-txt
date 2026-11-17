"""Besättningsstationer. Lägg till nya system här."""
from .base import Station
from .bridge import BridgeWatch
from .daylight import LightWatch
from .engineering import EngineeringStation
from .navigation import NavigationStation, SetCourse, SetDepth, SetSpeed
from .officer import OfficerStation
from .periscope import PeriscopeWatch
from .plot import PlotTeam, QuerySolution, ShowPlot
from .radio import RadioStation
from .sonar_room import SonarRoom
from .starpom import FirstOfficer
from .torpedo_room import TorpedoRoom
from .training import TrainingOfficer

# Ordningen är uppdateringsordningen varje tick:
# egen rörelse och teknik först, sedan sensorer, sedan analys och vapen.
DEFAULT_STATIONS: list[type[Station]] = [
    NavigationStation, EngineeringStation, SonarRoom, OfficerStation, PeriscopeWatch, BridgeWatch,
    RadioStation, PlotTeam, TorpedoRoom, TrainingOfficer, FirstOfficer, LightWatch,
]

__all__ = [
    "Station", "DEFAULT_STATIONS",
    "NavigationStation", "SetCourse", "SetSpeed", "SetDepth",
    "EngineeringStation", "SonarRoom", "OfficerStation", "PeriscopeWatch", "BridgeWatch", "RadioStation",
    "PlotTeam", "QuerySolution", "ShowPlot", "TorpedoRoom", "TrainingOfficer", "FirstOfficer",
    "LightWatch",
]
