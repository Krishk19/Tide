import time
from typing import Callable

from .platform import Platform
from .ui.port import UiPort


class Enforcer:
    def __init__(self, p: Platform, ui: UiPort, sleep: Callable[[float], None] = time.sleep) -> None:
        self.p, self.ui, self.sleep = p, ui, sleep

    def act(self, action: str, target: dict, title: str, persistent: bool = False) -> str:
        result = "none"
        if action == "kill" and target.get("pid"):
            self.p.kill(target["pid"])
            result = "killed"
        elif action == "close_tab" and target.get("hwnd"):
            self.p.close_tab(target["hwnd"])
            self.sleep(0.3)
            still = self.p.browser_host(target["hwnd"], target.get("process") or "")
            if still and still == target.get("host") and target.get("pid"):
                self.p.kill(target["pid"])
                result = "killed_browser"
            else:
                result = "closed"
        elif action == "overlay":
            result = "shown"
        if action != "none":
            self.ui.block(title, persistent)
        return result
