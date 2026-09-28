import time

import win32api
import win32con
import win32gui


def close_tab(hwnd: int) -> None:
    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)                     # unlock SetForegroundWindow
    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.05)
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord("W"), 0, 0, 0)
    win32api.keybd_event(ord("W"), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
