import { seatsGrid } from "../state";
import type { Room, Seat } from "../types";

function lobbyNote(s: Seat): string {
  if (s.state === "blocked") return "Internet on";
  if (s.preflight.extensions?.length) return `${s.preflight.extensions[0].replace("GitHub ", "")} found`;
  if (s.state === "lobby") return "Checking…";
  return "Ready";
}

export default function SeatGrid({ room, mode, filter = "all", onOpen }:
  { room: Room; mode: "lobby" | "live"; filter?: string; onOpen?: (id: number) => void }) {
  return (
    <div className="seats">
      {seatsGrid(room).map((s) => {
        if ("placeholder" in s)
          return <div key={`p${s.seat_no}`} className="seat placeholder"><span className="no">{String(s.seat_no).padStart(2, "0")}</span></div>;
        const cls = ["seat", s.status, !s.simulated ? "real" : "", filter !== "all" && s.status !== filter ? "dim" : ""].join(" ");
        return (
          <div key={s.id} className={cls} onClick={() => onOpen?.(s.id)}>
            <span className="no">{String(s.seat_no).padStart(2, "0")}</span>
            <span className="roll">{s.roll.slice(-3)}</span>
            {mode === "live" && s.flags > 0 && <span className="badge">{s.flags}</span>}
            <span className="now">{mode === "lobby" ? lobbyNote(s) : s.status === "done" ? "Submitted" : s.fg_app}</span>
          </div>
        );
      })}
    </div>
  );
}
