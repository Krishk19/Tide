from typing import Callable


class HeadlessUI:
    def __init__(self, out: Callable[[str], None] = print) -> None:
        self.out = out

    def show_join(self, server, error=None): self.out(f"[join] server={server}" + (f" error={error}" if error else ""))
    def show_preflight(self, checks): self.out("[preflight] " + " ".join(f"{c['state']}:{c['label']}" for c in checks))
    def start(self, seat_no, set_name, ends_at_local, folder): self.out(f"[start] PC-{seat_no:02d} set {set_name} folder {folder}")
    def set_ends_at(self, ends_at_local): self.out(f"[time] ends_at={ends_at_local:.0f}")
    def notice(self, text): self.out(f"[notice] {text}")
    def block(self, title, persistent=False): self.out(f"[block] {title}" + (" (until offline)" if persistent else ""))
    def unblock(self): self.out("[unblock]")
    def done(self, n_files, at): self.out(f"[done] {n_files} files at {at}")
    def error(self, text): self.out(f"[error] {text}")
    def quit(self): self.out("[quit]")
