import time

import psutil
import win32clipboard
import win32con


def removable_drives() -> set[str]:
    return {p.mountpoint for p in psutil.disk_partitions(all=False) if "removable" in p.opts}


def clipboard_seq() -> int:
    return win32clipboard.GetClipboardSequenceNumber()


def clipboard_text() -> str | None:
    for _ in range(3):
        try:
            win32clipboard.OpenClipboard()
        except Exception:
            time.sleep(0.05)
            continue
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return None
        finally:
            win32clipboard.CloseClipboard()
    return None
