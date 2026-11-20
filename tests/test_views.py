"""Vyregistret (ui/views.py): Tab-ordningen och orden som öppnar vyerna."""
from ui.boat import BoatScreen
from ui.bridge import BridgeScreen
from ui.cabin import CabinScreen
from ui.chart import ChartScreen
from ui.logview import LogScreen
from ui.periscope import PeriscopeScreen
from ui.sonar import SonarScreen
from ui.views import CENTRAL_WORDS, REGISTRY, SCREENS, ViewContext, manual_words, tab_order, view_for


def test_tab_order_follows_the_situation():
    assert tab_order(ViewContext()) == (ChartScreen, SonarScreen, BoatScreen, PeriscopeScreen)
    assert tab_order(ViewContext(big=True))[0] is LogScreen
    assert tab_order(ViewContext(big=True, command="starpom"))[:2] == (CabinScreen, LogScreen)
    # med folk på bryggan kommer bryggan före periskopbilden (kikaren)
    assert tab_order(ViewContext(bridge="manned"))[-2:] == (BridgeScreen, PeriscopeScreen)


def test_every_word_opens_exactly_one_view():
    seen: dict[str, object] = {}
    for v in REGISTRY:
        for w in v.words:
            assert w not in seen, f"{w} öppnar två vyer"
            assert w not in CENTRAL_WORDS
            seen[w] = v
    assert view_for("sjökort").screen is ChartScreen
    assert view_for("telegram").word_action == "_telegrams"
    assert view_for("centralen") is None


def test_manual_words_open_a_view_and_every_screen_is_a_view():
    for w in manual_words()[1:]:
        assert view_for(w) is not None
    assert set(SCREENS) == {ChartScreen, SonarScreen, BoatScreen, PeriscopeScreen, BridgeScreen,
                            CabinScreen, LogScreen}
