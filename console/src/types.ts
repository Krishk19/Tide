export type Status = "ok" | "warn" | "crit" | "off" | "wait" | "done";
export type Severity = "info" | "medium" | "high" | "critical";

export interface Seat {
  id: number; seat_no: number; roll: string; set: string | null; state: string; status: Status;
  flags: number; fg_app: string; simulated: boolean;
  preflight: { internet?: boolean; extensions?: string[]; denied_closed?: string[]; inventory_count?: number };
}
export interface Flag {
  id: number; seat_id: number; seat_no: number; ts: number; kind: string; severity: Severity; title: string;
  source: string; label: string | null; confidence: number | null; action: string;
  status: "open" | "dismissed" | "confirmed"; has_shot: boolean; data: Record<string, unknown>;
}
export interface Exam {
  id: number; title: string; duration_s: number; join_code: string; state: "lobby" | "live" | "ended";
  started_at: number | null; ends_at: number | null; apps: string[];
}
export interface EventItem { id: number; seat_id: number; ts: number; kind: string; text: string }
export type ServerMsg =
  | { t: "hello"; exam: Exam | null; seats: Seat[]; flags: Flag[]; mode: string; server_time: number }
  | { t: "seat"; seat: Seat } | { t: "flag"; flag: Flag } | { t: "event"; event: EventItem }
  | { t: "exam"; exam: Exam } | { t: "connected"; value: boolean };
export interface Room {
  exam: Exam | null; seats: Record<number, Seat>; flags: Record<number, Flag>; mode: string;
  clockOffset: number; lastEvent: EventItem | null; connected: boolean;
}
export type TimelineItem = ({ type: "event" } & EventItem) | ({ type: "flag" } & Flag);
export interface SeatDetail { seat: Seat; timeline: TimelineItem[]; growth: { ts: number; lines: number }[];
  files: { path: string; lines: number }[] }
export interface Results {
  rows: { seat_id: number; seat_no: number; roll: string; set: string | null; submitted_at: number | null;
    flags: { kind: string; severity: Severity; title: string }[]; max_match: number | null }[];
  pairs: { a: number; b: number | null; b_path: string | null; pct: number }[];
  flag_counts: Record<string, number>;
}
