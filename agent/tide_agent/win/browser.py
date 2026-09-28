import uiautomation as auto

from tide_agent.urlhost import host_from_value

ADDRESS_NAMES = ("Address and search bar", "Search or enter web address", "Search with Google or enter address",
                 "Search or enter address", "Address field")


def browser_host(hwnd: int, process: str) -> str | None:
    try:
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(hwnd)
            edit = None
            for name in ADDRESS_NAMES:
                c = root.EditControl(searchDepth=14, Name=name)
                if c.Exists(0, 0):
                    edit = c
                    break
            if edit is None:
                c = root.EditControl(searchDepth=14)
                edit = c if c.Exists(0, 0) else None
            if edit is None:
                return None
            return host_from_value(edit.GetValuePattern().Value)
    except Exception:
        return None
