import { describe, expect, it } from "vitest";
import { counts, emptyRoom, fmtClock, openAlerts, reduce, remaining, seatsGrid } from "./state";
import type { Flag, Seat } from "./types";

const seat = (id: number, status: Seat["status"]): Seat => ({
  id, seat_no: id, roll: `R${id}`, set: "A", state: "live", status, flags: 0, fg_app: "VS Code",
  simulated: false, preflight: {},
});
const flag = (id: number, severity: Flag["severity"], status: Flag["status"] = "open", ts = id): Flag => ({
  id, seat_id: 1, seat_no: 1, ts, kind: "x", severity, title: `f${id}`, source: "rule", label: null,
  confidence: null, action: "none", status, has_shot: false, data: {},
});

describe("room state", () => {
  it("hello replaces the room and measures clock offset", () => {
    const r = reduce(emptyRoom, { t: "hello", exam: null, seats: [seat(1, "ok")], flags: [flag(1, "high")],
      mode: "jev", server_time: 1010 }, 1000);
    expect(r.seats[1].status).toBe("ok");
    expect(r.clockOffset).toBe(10);
    expect(r.mode).toBe("jev");
  });

  it("seat and flag updates upsert", () => {
    let r = reduce(emptyRoom, { t: "seat", seat: seat(2, "ok") });
    r = reduce(r, { t: "seat", seat: seat(2, "crit") });
    r = reduce(r, { t: "flag", flag: flag(5, "critical") });
    expect(r.seats[2].status).toBe("crit");
    expect(Object.keys(r.flags)).toEqual(["5"]);
  });

  it("open alerts: newest first, no info, no reviewed", () => {
    let r = emptyRoom;
    for (const f of [flag(1, "medium"), flag(2, "info"), flag(3, "high", "dismissed"), flag(4, "critical")])
      r = reduce(r, { t: "flag", flag: f });
    expect(openAlerts(r).map((f) => f.id)).toEqual([4, 1]);
  });

  it("counts buckets", () => {
    let r = emptyRoom;
    for (const s of [seat(1, "ok"), seat(2, "done"), seat(3, "warn"), seat(4, "crit"), seat(5, "off"), seat(6, "wait")])
      r = reduce(r, { t: "seat", seat: s });
    expect(counts(r)).toEqual({ ok: 2, warn: 1, crit: 1, off: 1 });
  });

  it("grid fills to 60 with placeholders", () => {
    const r = reduce(emptyRoom, { t: "seat", seat: seat(7, "ok") });
    const g = seatsGrid(r);
    expect(g.length).toBe(60);
    expect("placeholder" in g[0]).toBe(true);
    expect(g[6]).toMatchObject({ id: 7 });
  });

  it("clock helpers", () => {
    expect(fmtClock(42 * 60 + 18)).toBe("42:18");
    expect(fmtClock(0)).toBe("0:00");
    const exam = { id: 1, title: "t", duration_s: 60, join_code: "X", state: "live" as const, started_at: 0,
      ends_at: 1100, apps: [], internet: "allowed" as const };
    expect(remaining(exam, 10, 1000)).toBe(90);
    expect(remaining(null, 0, 1000)).toBe(0);
  });
});
