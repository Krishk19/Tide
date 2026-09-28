import json
import threading
from pathlib import Path


class Outbox:
    """Messages that couldn't be sent. On disk, so they survive an agent restart."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, message: dict) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(message) + "\n")

    def drain(self) -> list[dict]:
        with self._lock:
            if not self.path.exists():
                return []
            lines = self.path.read_text(encoding="utf-8").splitlines()
            self.path.unlink()
        return [json.loads(line) for line in lines if line.strip()]
