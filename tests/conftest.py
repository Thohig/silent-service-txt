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
