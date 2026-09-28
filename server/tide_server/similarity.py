import csv
import io
import json
from collections import Counter
from datetime import datetime
from itertools import combinations

from sqlmodel import Session, select

from tide_common.fingerprint import fingerprints, similarity

from tide_server.models import Exam, Flag, Seat, Snapshot, Submission
from tide_server.serialize import KIND_TEXT


def count_lines(text: str) -> int:
    return len(text.splitlines())


def latest_texts(db: Session, seat_id: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for s in db.exec(select(Snapshot).where(Snapshot.seat_id == seat_id).order_by(Snapshot.id)).all():
        out[s.path] = s.text
    return out


def total_lines(db: Session, seat_id: int) -> int:
    return sum(count_lines(t) for t in latest_texts(db, seat_id).values())


def compute_pairs(db: Session, exam_id: int, min_pct: int = 40) -> list[dict]:
    seats = db.exec(select(Seat).where(Seat.exam_id == exam_id)).all()
    fps = {}
    for s in seats:
        text = "\n".join(latest_texts(db, s.id).values())
        fp = fingerprints(text)
        if fp:
            fps[s.seat_no] = fp
    pairs = []
    for a, b in combinations(sorted(fps), 2):
        pct = round(similarity(fps[a], fps[b]) * 100)
        if pct >= min_pct:
            pairs.append({"a": a, "b": b, "b_path": None, "pct": pct})
    return sorted(pairs, key=lambda p: -p["pct"])


def results(db: Session, exam: Exam) -> dict:
    seats = db.exec(select(Seat).where(Seat.exam_id == exam.id).order_by(Seat.seat_no)).all()
    by_id = {s.id: s for s in seats}
    flags = [f for f in db.exec(select(Flag)).all() if f.seat_id in by_id and f.status != "dismissed"]
    pairs = compute_pairs(db, exam.id)
    for f in flags:
        if f.kind == "old_code":
            d = json.loads(f.data_json)
            pairs.append({"a": by_id[f.seat_id].seat_no, "b": None, "b_path": d.get("source_path"),
                          "pct": d.get("pct", 0)})
    pairs.sort(key=lambda p: -p["pct"])
    best: dict[int, int] = {}
    for p in pairs:
        for n in (p["a"], p["b"]):
            if n is not None:
                best[n] = max(best.get(n, 0), p["pct"])
    subs = {s.seat_id: s for s in db.exec(select(Submission)).all()}
    rows = []
    for s in seats:
        rows.append({"seat_id": s.id, "seat_no": s.seat_no, "roll": s.roll, "set": s.set_name,
                     "submitted_at": subs[s.id].ts if s.id in subs else None,
                     "flags": [{"kind": f.kind, "severity": f.severity, "title": f.title}
                               for f in flags if f.seat_id == s.id],
                     "max_match": best.get(s.seat_no)})
    counts = Counter(KIND_TEXT.get(f.kind, f.kind) for f in flags)
    return {"rows": rows, "pairs": pairs, "flag_counts": dict(counts.most_common())}


def results_csv(data: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["seat", "roll", "set", "submitted_at", "flags", "max_match"])
    for r in data["rows"]:
        at = datetime.fromtimestamp(r["submitted_at"]).strftime("%H:%M:%S") if r["submitted_at"] else ""
        w.writerow([f"PC-{r['seat_no']:02d}", r["roll"], r["set"] or "", at,
                    "; ".join(f["title"] for f in r["flags"]),
                    "" if r["max_match"] is None else r["max_match"]])
    return buf.getvalue()
