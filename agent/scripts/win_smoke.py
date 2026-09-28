"""Run on a Windows PC: python agent/scripts/win_smoke.py  (switch windows while it runs)."""
import time

from tide_agent.win import WinPlatform

p = WinPlatform()
print("processes:", len(p.processes()))
print("adapters:", p.adapters())
print("internet:", p.internet())
print("usb:", p.removable_drives(), "clipboard seq:", p.clipboard_seq())
shot = p.screenshot()
print("screenshot bytes:", len(shot or b""))
for _ in range(20):
    w = p.foreground()
    host = p.browser_host(w.hwnd, w.process) if w else None
    print(f"{w.process if w else None!s:24} {host!s:22} {w.title[:60] if w else ''}")
    time.sleep(1)
