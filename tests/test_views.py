"""Vyregistret (ui/views.py): Tab-ordningen och orden som öppnar vyerna."""
from ui.boat import BoatScreen
from ui.bridge import BridgeScreen
from ui.cabin import CabinScreen
from ui.central import CentralScreen
from ui.chart import ChartScreen
from ui.logview import LogScreen
from ui.overview import OverviewScreen
from ui.periscope import PeriscopeScreen
from ui.sonar import SonarScreen
from ui.views import REGISTRY, SCREENS, ViewContext, manual_words, tab_order, view_for


def test_tab_order_follows_the_situation():
    # litet fönster: loggen är huvudvyn, översikten en vy först i ordningen
    assert tab_order(ViewContext()) == (OverviewScreen, CentralScreen, ChartScreen, SonarScreen,
                                        BoatScreen, PeriscopeScreen)
    # stort fönster: översikten är huvudvyn, centralen först och loggboken en vy
    assert tab_order(ViewContext(big=True))[:3] == (CentralScreen, LogScreen, ChartScreen)
    assert OverviewScreen not in tab_order(ViewContext(big=True))
    assert tab_order(ViewContext(big=True, command="starpom"))[:3] == (CabinScreen, CentralScreen, LogScreen)
    # med folk på bryggan kommer bryggan före periskopbilden (kikaren)
    assert tab_order(ViewContext(bridge="manned"))[-2:] == (BridgeScreen, PeriscopeScreen)


def test_every_word_opens_exactly_one_view():
    seen: dict[str, object] = {}
    for v in REGISTRY:
        for w in v.words:
            assert w not in seen, f"{w} öppnar två vyer"
            seen[w] = v
    assert view_for("sjökort").screen is ChartScreen
    assert view_for("telegram").word_action == "_telegrams"
    assert view_for("centralen").screen is CentralScreen
    assert view_for("översikt").word_action == "_overview_word"     # stort fönster: huvudvyn
    assert view_for("läge") is None                 # plottets order (läge S-1)


def test_manual_words_open_a_view_and_every_screen_is_a_view():
    for w in manual_words():
        assert view_for(w) is not None
    assert set(SCREENS) == {ChartScreen, SonarScreen, BoatScreen, PeriscopeScreen, BridgeScreen,
                            CabinScreen, LogScreen, OverviewScreen, CentralScreen}
