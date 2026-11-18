"""Eget fönster (fonster.py): servern visar vår sida och stänger spelet (kräver --extra fonster)."""
import shlex
import sys
import time
import urllib.request

import pytest

pytest.importorskip("textual_serve")

import fonster  # noqa: E402


def test_server_visar_sidan_utan_natet():
    server = fonster._ServerThread(shlex.join([sys.executable, "-c", "pass"]), fonster._free_port())
    server.start()
    assert server.ready.wait(10)
    try:
        html = urllib.request.urlopen(f"http://127.0.0.1:{server.port}/?fontsize=14").read().decode()
    finally:
        server.stop()
    assert "<title>K-114</title>" in html
    assert "Menlo" in html                    # typsnittet lokalt
    assert "googleapis" not in html           # inget från nätet
    assert "pywebview.api.avsluta" in html    # fönstret stängs när spelet slutar
    assert 'data-font-size="14"' in html


def test_server_stannar():
    server = fonster._ServerThread(shlex.join([sys.executable, "-c", "pass"]), fonster._free_port())
    server.start()
    assert server.ready.wait(10)
    server.stop()
    time.sleep(0.2)
    assert not server.loop.is_running()
