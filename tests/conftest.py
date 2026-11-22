"""Långsamma tester (`@pytest.mark.slow`: hela spel, statistik över frön, uppvärmning,
gränssnitt) körs bara med `--slow`."""
import pytest


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="kör även de långsamma testerna")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    skip = pytest.mark.skip(reason="långsamt test, kör med --slow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def perfect_torpedoes(monkeypatch):
    """Egna torpeder utan gyrofel, blindgångare och förtidsdetonationer: för tester av geometri och
    rapporter som annars skulle bero på slumpen."""
    from sim import weapons
    monkeypatch.setattr(weapons, "GYRO_SIGMA_DEG", 0.0)
    monkeypatch.setattr(weapons, "DUD_P", 0.0)
    monkeypatch.setattr(weapons, "PREMATURE_P", 0.0)
