"""Vyregistret (ui/views.py): Tab-ordningen och orden som öppnar vyerna."""
from ui.boat import BoatScreen
from ui.bridge import BridgeScreen
from ui.cabin import CabinScreen
from ui.central import CentralScreen
from ui.chart import ChartScreen
from ui.periscope import PeriscopeScreen
from ui.sonar import SonarScreen
from ui.views import REGISTRY, SCREENS, ViewContext, manual_words, tab_order, view_for


def test_tab_order_follows_the_situation():
    # översikten är huvudskärmen och loggboken ett lager (PageUp): ingen av dem i Tab-ordningen
    order = (CentralScreen, ChartScreen, SonarScreen, BoatScreen, PeriscopeScreen)
    assert tab_order(ViewContext()) == order
    assert tab_order(ViewContext(big=True)) == order
    assert tab_order(ViewContext(command="starpom"))[:2] == (CabinScreen, CentralScreen)
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
    assert view_for("översikt").word_action == "_overview_word"     # huvudskärmen
    assert view_for("logg").word_action == "_log_word" and view_for("logg").screen is None
    assert view_for("läge") is None                 # plottets order (läge S-1)


def test_manual_words_open_a_view_and_every_screen_is_a_view():
    for w in manual_words():
        assert view_for(w) is not None
    assert set(SCREENS) == {ChartScreen, SonarScreen, BoatScreen, PeriscopeScreen, BridgeScreen,
                            CabinScreen, CentralScreen}
