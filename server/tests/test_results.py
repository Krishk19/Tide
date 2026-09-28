from sqlmodel import select

from tide_server.burst import burst_lines
from tide_server.exam_service import pair_seat
from tide_server.models import Flag, Seat
from tide_server.similarity import compute_pairs, results, results_csv

A = "\n".join(["int main() {", "  int total = 0;"] + [f"  total += arr[{i}] * weight[{i}];" for i in range(30)] + ["  return total;", "}"])
B = A.replace("total", "sum").replace("weight", "w")


def test_burst_rule():
    assert burst_lines(10, 55) == 45
    assert burst_lines(10, 40) is None
    assert burst_lines(0, 200) == 200


async def test_snapshot_burst_flags_big_jump_only(ctx, paired, hub):
    seat, _ = paired
    await ctx.ingest.handle(seat.id, {"t": "snapshot", "ts": 10, "files": [{"path": "main.c", "text": "x\n" * 5, "sha": "1"}]})
    await ctx.ingest.handle(seat.id, {"t": "snapshot", "ts": 40, "files": [{"path": "main.c", "text": "x\n" * 60, "sha": "2"}]})
    with ctx.db() as db:
        f = db.exec(select(Flag).where(Flag.kind == "code_burst")).one()
    assert f.title == "Code burst · +55 lines" and f.severity == "medium"


def test_submit_saves_zip_and_locks_seat(client, ctx, paired):
    seat, token = paired
    r = client.post("/api/submit", data={"token": token, "auto": "false"},
                    files={"file": ("s.zip", b"PK\x03\x04zip", "application/zip")})
    assert r.json() == {"ok": True}
    with ctx.db() as db:
        assert db.get(Seat, seat.id).state == "submitted"
    assert (ctx.settings.data_dir / "submissions" / "PC07_22BCS107.zip").read_bytes() == b"PK\x03\x04zip"
    assert client.post("/api/submit", data={"token": "bad"}, files={"file": ("s.zip", b"x")}).status_code == 401


async def test_pairs_and_results(ctx, exam):
    with ctx.db() as db:
        s1, _ = pair_seat(db, exam.join_code, "R1", 14, "")
        s2, _ = pair_seat(db, exam.join_code, "R2", 16, "")
        s3, _ = pair_seat(db, exam.join_code, "R3", 20, "")
    await ctx.ingest.handle(s1.id, {"t": "snapshot", "ts": 1, "files": [{"path": "main.c", "text": A, "sha": "a"}]})
    await ctx.ingest.handle(s2.id, {"t": "snapshot", "ts": 1, "files": [{"path": "main.c", "text": B, "sha": "b"}]})
    await ctx.ingest.handle(s3.id, {"t": "snapshot", "ts": 1, "files": [{"path": "main.py", "text": "print('hi')\n", "sha": "c"}]})
    with ctx.db() as db:
        pairs = compute_pairs(db, exam.id)
        data = results(db, exam)
    assert pairs[0]["a"] == 14 and pairs[0]["b"] == 16 and pairs[0]["pct"] >= 80
    rows = {r["seat_no"]: r for r in data["rows"]}
    assert rows[14]["max_match"] >= 80 and rows[20]["max_match"] is None
    csv = results_csv(data)
    assert csv.splitlines()[0] == "seat,roll,set,submitted_at,flags,max_match"
    assert "PC-14,R1" in csv


def test_results_endpoints(teacher, exam):
    assert teacher.get("/api/teacher/results").status_code == 200
    r = teacher.get("/api/teacher/results.csv")
    assert r.headers["content-type"].startswith("text/csv")
