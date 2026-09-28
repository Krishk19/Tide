from functools import lru_cache

import psutil
import win32api
import win32gui
import win32process

from tide_agent.platform import WindowInfo


@lru_cache(maxsize=512)
def pe_info(exe: str) -> tuple[str, str]:
    try:
        lang, cp = win32api.GetFileVersionInfo(exe, "\\VarFileInfo\\Translation")[0]
        base = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\"
        desc = win32api.GetFileVersionInfo(exe, base + "FileDescription") or ""
        orig = win32api.GetFileVersionInfo(exe, base + "OriginalFilename") or ""
        return str(desc), str(orig)
    except Exception:
        return "", ""


def _real_pid(hwnd: int, pid: int, name: str) -> int:
    if name.lower() != "applicationframehost.exe":
        return pid
    found = []

    def cb(child, _):
        _, cpid = win32process.GetWindowThreadProcessId(child)
        if cpid != pid:
            found.append(cpid)
    try:
        win32gui.EnumChildWindows(hwnd, cb, None)
    except Exception:
        pass
    return found[0] if found else pid


def foreground() -> WindowInfo | None:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    title = win32gui.GetWindowText(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        name = psutil.Process(pid).name()
        pid = _real_pid(hwnd, pid, name)
        proc = psutil.Process(pid)
        name, exe = proc.name(), proc.exe()
    except psutil.Error:
        name, exe = "", ""
    desc, orig = pe_info(exe) if exe else ("", "")
    return WindowInfo(hwnd, pid, name, exe, title, desc, orig)
