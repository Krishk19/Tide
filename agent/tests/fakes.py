from tide_agent.platform import AdapterInfo, ProcInfo, WindowInfo


class FakePlatform:
    def __init__(self):
        self.window: WindowInfo | None = WindowInfo(1, 10, "Code.exe", "C:/code.exe", "main.c - 22BCS107 - Visual Studio Code")
        self.hosts: dict[int, str | None] = {}
        self.host_reads = 0
        self.procs: dict[int, ProcInfo] = {10: ProcInfo(10, "Code.exe")}
        self.killed: list[int] = []
        self.ads = {"Ethernet": AdapterInfo("Ethernet", True), "Wi-Fi": AdapterInfo("Wi-Fi", False, wifi=True)}
        self.online = False
        self.peers = []
        self.drives: set[str] = set()
        self.clip_seq = 1
        self.clip: str | None = None
        self.closed_tabs: list[int] = []
        self.shot: bytes | None = b"\xff\xd8jpeg"

    def foreground(self): return self.window
    def browser_host(self, hwnd, process):
        self.host_reads += 1
        return self.hosts.get(hwnd)
    def processes(self): return dict(self.procs)
    def kill(self, pid):
        self.killed.append(pid)
        self.procs.pop(pid, None)
    def adapters(self): return dict(self.ads)
    def internet(self): return self.online
    def lan_peers(self, server_ip): return [p for p in self.peers if p.ip != server_ip]
    def removable_drives(self): return set(self.drives)
    def clipboard_seq(self): return self.clip_seq
    def clipboard_text(self): return self.clip
    def close_tab(self, hwnd): self.closed_tabs.append(hwnd)
    def screenshot(self): return self.shot
