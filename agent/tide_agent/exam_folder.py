import hashlib
import io
import zipfile
from pathlib import Path

from .inventory import TEXT_EXTS


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


class ExamFolder:
    """C:\\Exam\\<roll>. Questions arrive here; snapshots and the submission come from here."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._sent: dict[str, str] = {}

    def write_files(self, files: list[tuple[str, bytes]]) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        written = 0
        for name, data in files:
            target = self.root / Path(name).name
            self._sent.setdefault(target.name, _sha(data))
            if target.exists():
                continue
            target.write_bytes(data)
            written += 1
        return written

    def _text_files(self) -> list[Path]:
        if not self.root.exists():
            return []
        return [p for p in sorted(self.root.rglob("*"))
                if p.is_file() and p.suffix.lower() in TEXT_EXTS and p.stat().st_size <= 1_000_000]

    def texts(self) -> dict[str, str]:
        return {p.relative_to(self.root).as_posix(): p.read_text(encoding="utf-8", errors="ignore")
                for p in self._text_files()}

    def changed_files(self) -> list[dict]:
        out = []
        for p in self._text_files():
            rel = p.relative_to(self.root).as_posix()
            data = p.read_bytes()
            sha = _sha(data)
            if self._sent.get(rel) != sha:
                self._sent[rel] = sha
                out.append({"path": rel, "text": data.decode("utf-8", errors="ignore"), "sha": sha})
        return out

    def file_count(self) -> int:
        return sum(1 for p in self.root.rglob("*") if p.is_file()) if self.root.exists() else 0

    def zip_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            if self.root.exists():
                for p in sorted(self.root.rglob("*")):
                    if p.is_file():
                        z.write(p, p.relative_to(self.root).as_posix())
        return buf.getvalue()
