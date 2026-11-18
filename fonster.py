"""Spela K-114 i ett eget fönster med ubåtsikonen i Docken (macOS).

    uv run --extra fonster fonster.py [--seed N] [--scenario NAMN] [--tyst]

Spelet körs som vanligt (`main.py`) men i en webbterminal: textual-serve startar det
på en ledig port på 127.0.0.1 och pywebview visar sidan i ett eget fönster. Ljudet spelas av
spelprocessen som förut. Fönstret stängs när spelet avslutas, och ⌘Q avslutar spelet.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICON = HERE / "ikon" / "k114-1024.png"
TEMPLATES = HERE / "ikon" / "webb"
TITLE = "K-114"
FONT_SIZE = 14
# 140 × 42 tecken i Menlo 14 (som K-114.app ställer Terminal på)
WIDTH, HEIGHT = 1190, 760


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _name_app() -> None:
    """Menyraden och Om-rutan säger K-114 i stället för Python (före pywebview)."""
    try:
        from Foundation import NSBundle
        info = NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = TITLE
    except Exception:
        pass


class _ServerThread(threading.Thread):
    """textual-serve i en egen tråd med egen händelseslinga (pywebview måste ha huvudtråden)."""

    def __init__(self, command: str, port: int) -> None:
        super().__init__(daemon=True, name="textual-serve")
        from textual_serve.server import Server
        self.server = Server(command, host="127.0.0.1", port=port, title=TITLE,
                             templates_path=TEMPLATES)
        self.port = port
        self.ready = threading.Event()
        self.loop = asyncio.new_event_loop()
        self.runner = None

    def run(self) -> None:
        from aiohttp import web
        asyncio.set_event_loop(self.loop)

        async def start() -> None:
            self.server.console.quiet = True  # ingen logga eller anslutningslogg i terminalen
            self.runner = web.AppRunner(await self.server._make_app())
            await self.runner.setup()
            await web.TCPSite(self.runner, "127.0.0.1", self.port).start()
            self.ready.set()

        self.loop.run_until_complete(start())
        self.loop.run_forever()

    def stop(self, timeout: float = 5.0) -> None:
        """Stäng servern; då stängs websocketen och textual-serve avslutar spelet."""
        if self.runner is None:
            return
        fut = asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop)
        try:
            fut.result(timeout)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)


def _end_children() -> None:
    """Avsluta spelprocesser som blivit kvar (om servern inte hann stänga dem)."""
    out = subprocess.run(["pgrep", "-P", str(os.getpid())], capture_output=True, text=True).stdout
    for pid in out.split():
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass


class _Api:
    """Det sidan når genom window.pywebview.api."""

    def __init__(self) -> None:
        self.window = None

    def avsluta(self) -> None:
        if self.window is not None:
            self.window.destroy()


def main() -> None:
    p = argparse.ArgumentParser(description="K-114 i eget fönster")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--scenario", default=None)
    p.add_argument("--tyst", action="store_true")
    args = p.parse_args()

    game = [sys.executable, str(HERE / "main.py")]
    if args.seed is not None:
        game += ["--seed", str(args.seed)]
    if args.scenario:
        game += ["--scenario", args.scenario]
    if args.tyst:
        game.append("--tyst")

    server = _ServerThread(shlex.join(game), _free_port())
    server.start()
    if not server.ready.wait(10):
        sys.exit("K-114: servern startade inte")

    _name_app()
    import webview

    done = threading.Event()

    def shut_down(*_) -> None:
        """Stäng servern och spelet, en gång, hur fönstret än stängs."""
        if done.is_set():
            return
        done.set()
        server.stop(timeout=3)
        _end_children()

    # ⌘Q avslutar Cocoa med exit() utan att webview.start() återvänder, så finally hinner
    # inte köras; därför också meddelandet före avslutningen.
    def on_terminate() -> None:
        from AppKit import NSApplicationWillTerminateNotification
        from Foundation import NSNotificationCenter
        NSNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
            NSApplicationWillTerminateNotification, None, None, shut_down)

    # SIGTERM/SIGHUP: Pythons signalhanterare körs inte medan Cocoa har huvudtråden, så
    # signalen skrivs till ett rör som serverns händelseslinga läser.
    def on_signal() -> None:
        os.read(wake_r, 64)
        threading.Thread(target=lambda: (shut_down(), os._exit(0)), daemon=True).start()

    wake_r, wake_w = os.pipe()
    os.set_blocking(wake_w, False)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: None)
    signal.set_wakeup_fd(wake_w)
    server.loop.call_soon_threadsafe(server.loop.add_reader, wake_r, on_signal)

    api = _Api()
    api.window = webview.create_window(
        TITLE, f"http://127.0.0.1:{server.port}/?fontsize={FONT_SIZE}",
        js_api=api, width=WIDTH, height=HEIGHT, min_size=(800, 500),
        background_color="#000000", text_select=False)
    try:
        webview.start(on_terminate, icon=str(ICON), private_mode=True)
    finally:
        shut_down()
    # pywebviews egna trådar (anrop från sidan, js) är inte daemon och kan hålla processen kvar.
    os._exit(0)


if __name__ == "__main__":
    main()
