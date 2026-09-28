"""A pretend student PC for dev on any OS. Type commands in the terminal to act out cheats."""
import io
import sys
import threading
from pathlib import Path

from .platform import AdapterInfo, Peer, ProcInfo, WindowInfo

OLD_CODE = "\n".join(["#include <stdio.h>", "#include <string.h>", "int is_private(int a, int b) {",
                      "    if (a == 10) return 1;", "    if (a == 172 && b >= 16 && b <= 31) return 1;",
                      "    if (a == 192 && b == 168) return 1;", "    return 0;", "}",
                      "char cls(int a) {", "    if (a < 128) return 'A';", "    if (a < 192) return 'B';",
                      "    if (a < 224) return 'C';", "    if (a < 240) return 'D';", "    return 'E';", "}",
                      "int main(void) {", "    int n, a, b, c, d;", '    scanf("%d", &n);',
                      "    while (n--) {", '        scanf("%d.%d.%d.%d", &a, &b, &c, &d);',
                      '        printf("%c %s\\n", cls(a), is_private(a, b) ? "private" : "public");',
                      "    }", "    return 0;", "}"])

HELP = "commands: code | ai | poe | app | wifi | wifi off | old | paste | usb | clip | help"


class FakePlatform:
    def __init__(self, home: Path, exam_root: Path | None = None, roll: str = "22BCS107") -> None:
        self.home = home
        self.old_dir = home / "old"
        self.old_dir.mkdir(parents=True, exist_ok=True)
        (self.old_dir / "dsa_lab5.cpp").write_text(OLD_CODE)
        self.ext_dir = home / ".vscode" / "extensions"
        (self.ext_dir / "github.copilot-1.250.0").mkdir(parents=True, exist_ok=True)
        self.exam_root, self.roll = exam_root, roll
        self._lock = threading.Lock()
        self.code_window()
        self.host: str | None = None
        self.procs = {1: ProcInfo(1, "explorer.exe"), 10: ProcInfo(10, "Code.exe")}
        self.wifi_on = False
        self.drives: set[str] = set()
        self.clip_seq, self.clip = 1, None
        self.log: list[str] = []

    # --- scripted actions -------------------------------------------------
    def code_window(self, title: str | None = None) -> None:
        self.window = WindowInfo(100, 10, "Code.exe", "C:/VS Code/Code.exe",
                                 title or f"main.c - {getattr(self, 'roll', '22BCS107')} - Visual Studio Code",
                                 "Visual Studio Code", "Code.exe")
        self.host = None

    def command(self, line: str) -> str:
        cmd = line.strip().lower()
        with self._lock:
            if cmd == "code":
                self.code_window()
            elif cmd == "ai":
                self.window, self.host = WindowInfo(200, 20, "chrome.exe", "", "ChatGPT", "Google Chrome"), "chatgpt.com"
                self.procs[20] = ProcInfo(20, "chrome.exe")
            elif cmd == "poe":
                self.window, self.host = WindowInfo(201, 20, "chrome.exe", "", "Fast AI Chat - Poe", "Google Chrome"), "poe.com"
                self.procs[20] = ProcInfo(20, "chrome.exe")
            elif cmd == "app":
                self.window = WindowInfo(300, 30, "notegpt.exe", "C:/Users/s/NoteGPT/notegpt.exe",
                                         "NoteGPT - AI Notes & Answers", "NoteGPT")
                self.procs[30] = ProcInfo(30, "notegpt.exe")
            elif cmd == "wifi":
                self.wifi_on = True
            elif cmd == "wifi off":
                self.wifi_on = False
            elif cmd == "old":
                self.code_window("dsa_lab5.cpp - old - Visual Studio Code")
            elif cmd == "paste":
                if self.exam_root:
                    (self.exam_root / self.roll / "main.c").write_text(OLD_CODE.replace("cls", "klass"))
            elif cmd == "usb":
                self.drives = {"E:\\"}
            elif cmd == "clip":
                self.clip_seq, self.clip = self.clip_seq + 1, OLD_CODE
            else:
                return HELP
        return f"ok: {cmd}"

    def read_stdin_forever(self) -> None:
        def loop():
            print(HELP, flush=True)
            for line in sys.stdin:
                print(self.command(line), flush=True)
        threading.Thread(target=loop, daemon=True).start()

    # --- Platform -----------------------------------------------------------
    def foreground(self): return self.window
    def browser_host(self, hwnd, process): return self.host
    def processes(self): return dict(self.procs)

    def kill(self, pid):
        with self._lock:
            self.procs.pop(pid, None)
            self.log.append(f"kill {pid}")
            if self.window.pid == pid:
                self.code_window()

    def adapters(self):
        return {"Ethernet": AdapterInfo("Ethernet", True),
                "Wi-Fi": AdapterInfo("Wi-Fi", self.wifi_on, True, "Redmi Note" if self.wifi_on else None)}

    def internet(self): return self.wifi_on
    def lan_peers(self, server_ip): return []
    def removable_drives(self): return set(self.drives)
    def clipboard_seq(self): return self.clip_seq
    def clipboard_text(self): return self.clip

    def close_tab(self, hwnd):
        with self._lock:
            self.log.append(f"close_tab {hwnd}")
            self.code_window()

    def screenshot(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return None
        img = Image.new("RGB", (640, 360), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 640, 28], fill="#DEE1E6")
        d.text((12, 8), self.host or self.window.title, fill="#333")
        d.text((220, 170), self.window.title, fill="#111")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        return buf.getvalue()
