from dataclasses import dataclass
from pathlib import Path

from tide_common.policy import DENY_PROCESSES
from tide_common.protocol import msg

from .inventory import Inventory, build_inventory
from .platform import Platform
from .watchers import scan_extensions


@dataclass
class PreflightResult:
    internet: bool
    extensions: list[str]
    denied_closed: list[str]
    inventory: Inventory


def run_preflight(p: Platform, ext_dir: Path, roots: list[Path], exam_root: Path,
                  inventory: Inventory | None = None) -> PreflightResult:
    closed = []
    for pid, pi in p.processes().items():
        name = DENY_PROCESSES.get(pi.name.lower()) or DENY_PROCESSES.get(pi.original_name.lower())
        if name:
            p.kill(pid)
            closed.append(name)
    return PreflightResult(internet=p.internet(), extensions=scan_extensions(ext_dir),
                           denied_closed=sorted(set(closed)),
                           inventory=inventory or build_inventory(roots, exclude=exam_root))


def preflight_message(r: PreflightResult) -> dict:
    return msg("preflight", internet=r.internet, extensions=r.extensions, denied_closed=r.denied_closed,
               inventory_count=len(r.inventory.files))


def running_checks() -> list[dict]:
    return [{"id": i, "label": label, "detail": "", "state": "run"} for i, label in
            (("internet", "Offline"), ("apps", "Apps"), ("extensions", "AI extensions"), ("files", "Files"))]


def preflight_checks(r: PreflightResult) -> list[dict]:
    return [
        {"id": "internet", "label": "Internet on" if r.internet else "Offline",
         "detail": "Disconnect Wi-Fi / hotspot to continue" if r.internet else "No internet on any adapter",
         "state": "fail" if r.internet else "ok"},
        {"id": "apps", "label": "Apps",
         "detail": f"Closed {', '.join(r.denied_closed)}" if r.denied_closed else "Nothing blocked running",
         "state": "ok"},
        {"id": "extensions", "label": f"{', '.join(r.extensions)} found" if r.extensions else "AI extensions",
         "detail": "Teacher has been told" if r.extensions else "None installed",
         "state": "warn" if r.extensions else "ok"},
        {"id": "files", "label": "Files indexed", "detail": f"{len(r.inventory.files)} files", "state": "ok"},
    ]
