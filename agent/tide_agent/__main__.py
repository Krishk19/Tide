import argparse
import asyncio
import sys
from pathlib import Path


class _Api:
    def __init__(self, app):
        self.app = app

    def join(self, code, roll, seat, server=""):
        return self.app.join_from_ui(code, roll, seat, server)

    def submit(self):
        return self.app.submit_from_ui()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="tide-agent", description="Tide student agent")
    ap.add_argument("--server", help="teacher HOST[:PORT] (skips LAN discovery)")
    ap.add_argument("--fake", action="store_true", help="simulated PC for dev on any OS; type commands here")
    ap.add_argument("--headless", action="store_true", help="no windows; print UI events")
    ap.add_argument("--code")
    ap.add_argument("--roll")
    ap.add_argument("--seat", type=int)
    ap.add_argument("--exam-root", type=Path)
    args = ap.parse_args(argv)

    from .main import AgentApp, AgentConfig
    if args.fake:
        from .fake import FakePlatform
        platform = FakePlatform(Path.home() / "TideFakePC")
        platform.read_stdin_forever()
    elif sys.platform == "win32":
        from .win import WinPlatform
        platform = WinPlatform()
    else:
        sys.exit("The Tide agent runs on Windows. Use --fake to simulate a student PC.")
    cfg = AgentConfig.from_args(args, fake=platform if args.fake else None)

    if args.headless:
        from .ui.headless import HeadlessUI
        asyncio.run(AgentApp(platform, HeadlessUI(), cfg).run_forever())
        return
    from .ui.webview_ui import WebviewUI
    ui = WebviewUI()
    app = AgentApp(platform, ui, cfg)
    ui.bind(_Api(app))
    ui.run(lambda: asyncio.run(app.run_forever()))


if __name__ == "__main__":
    main()
