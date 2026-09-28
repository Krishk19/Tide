import type { Exam, Flag, Room, Seat, ServerMsg } from "./types";

export const emptyRoom: Room = { exam: null, seats: {}, flags: {}, mode: "heuristics", clockOffset: 0,
  lastEvent: null, connected: false };

const nowSec = () => Date.now() / 1000;

export function reduce(room: Room, m: ServerMsg, now = nowSec()): Room {
  switch (m.t) {
    case "hello":
      return { ...room, exam: m.exam, mode: m.mode, clockOffset: m.server_time - now, connected: true,
        seats: Object.fromEntries(m.seats.map((s) => [s.id, s])),
        flags: Object.fromEntries(m.flags.map((f) => [f.id, f])) };
    case "seat": return { ...room, seats: { ...room.seats, [m.seat.id]: m.seat } };
    case "flag": return { ...room, flags: { ...room.flags, [m.flag.id]: m.flag } };
    case "event": return { ...room, lastEvent: m.event };
    case "exam": return { ...room, exam: m.exam };
    case "connected": return { ...room, connected: m.value };
  }
}

export function openAlerts(room: Room): Flag[] {
  return Object.values(room.flags).filter((f) => f.status === "open" && f.severity !== "info")
    .sort((a, b) => b.ts - a.ts || b.id - a.id);
}

export function counts(room: Room) {
  const c = { ok: 0, warn: 0, crit: 0, off: 0 };
  for (const s of Object.values(room.seats)) {
    if (s.status === "ok" || s.status === "done") c.ok++;
    else if (s.status === "warn") c.warn++;
    else if (s.status === "crit") c.crit++;
    else if (s.status === "off") c.off++;
  }
  return c;
}

export function seatsGrid(room: Room, size = 60): (Seat | { seat_no: number; placeholder: true })[] {
  const byNo = new Map(Object.values(room.seats).map((s) => [s.seat_no, s]));
  const max = Math.max(size, ...byNo.keys());
  return Array.from({ length: max }, (_, i) => byNo.get(i + 1) ?? { seat_no: i + 1, placeholder: true as const });
}

export function remaining(exam: Exam | null, offset: number, now = nowSec()): number {
  if (!exam?.ends_at) return 0;
  return Math.max(0, Math.round(exam.ends_at - (now + offset)));
}

export function fmtClock(sec: number): string {
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}
