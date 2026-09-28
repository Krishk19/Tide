import json
import threading
from pathlib import Path

import webview

WEB = Path(__file__).parent / "web"


class WebviewUI:
    def __init__(self) -> None:
        screen = webview.screens[0] if webview.screens else None
        sw, sh = (screen.width, screen.height) if screen else (1920, 1080)
        self._persistent = False
        self.main = webview.create_window("Tide", str(WEB / "index.html"), width=440, height=600, resizable=False)
        self.pill = webview.create_window("Tide timer", str(WEB / "pill.html"), width=460, height=60,
                                          x=(sw - 460) // 2, y=10, frameless=True, on_top=True,
                                          hidden=True, easy_drag=True, resizable=False)
        self.overlay = webview.create_window("Tide", str(WEB / "overlay.html"), width=sw, height=sh, x=0, y=0,
                                             frameless=True, on_top=True, hidden=True, resizable=False)

    def bind(self, api) -> None:
        self.main.expose(api.join)
        self.pill.expose(api.submit)

    def run(self, func) -> None:
        webview.start(func)

    @staticmethod
    def _js(win, fn: str, *args) -> None:
        win.evaluate_js(f"window.tide && tide.{fn}(...{json.dumps(list(args))})")

    def show_join(self, server, error=None): self._js(self.main, "showJoin", server, error)
    def show_preflight(self, checks): self._js(self.main, "showPreflight", checks)

    def start(self, seat_no, set_name, ends_at_local, folder):
        self.main.hide()
        self.pill.show()
        self._js(self.pill, "start", f"PC-{seat_no:02d}", f"Set {set_name}", ends_at_local * 1000)

    def set_ends_at(self, ends_at_local): self._js(self.pill, "setEnds", ends_at_local * 1000)
    def notice(self, text): self._js(self.pill, "notice", text)

    def block(self, title, persistent=False):
        self._persistent = persistent
        self._js(self.overlay, "block", title, persistent)
        self.overlay.show()
        if not persistent:
            threading.Timer(4.0, self._auto_hide).start()

    def _auto_hide(self):
        if not self._persistent:
            self.overlay.hide()

    def unblock(self):
        self._persistent = False
        self.overlay.hide()

    def done(self, n_files, at):
        self.pill.hide()
        self.main.show()
        self._js(self.main, "done", n_files, at)
        threading.Timer(10.0, self.quit).start()

    def error(self, text): self._js(self.main, "error", text)

    def quit(self):
        for w in (self.overlay, self.pill, self.main):
            try:
                w.destroy()
            except Exception:
                pass
