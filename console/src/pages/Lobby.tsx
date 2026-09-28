import { api } from "../api";
import SeatGrid from "../components/SeatGrid";
import TopBar from "../components/TopBar";
import type { Page } from "../App";
import type { Room } from "../types";

export default function Lobby({ room, page, onPage, onOpen }:
  { room: Room; page: Page; onPage: (p: Page) => void; onOpen: (id: number) => void }) {
  const seats = Object.values(room.seats);
  const joined = seats.filter((s) => s.state !== "lobby").length;
  const ready = seats.filter((s) => s.state === "ready").length;
  const exam = room.exam;
  return (
    <section>
      <TopBar room={room} page={page} onPage={onPage} />
      <div className="page lobby">
        <div className="card joincard">
          <div className="sub">Join code</div>
          <div className="code">{exam?.join_code ?? "——————"}</div>
          <div className="sub mono" style={{ fontSize: 12, marginTop: -10 }}>Students: open Tide, enter this code</div>
          <hr className="sep" style={{ margin: "4px 0" }} />
          <div className="joined">{joined}<small> / 60</small></div>
          <div className="bar"><i style={{ width: `${Math.min(100, (joined / 60) * 100)}%` }} /></div>
          <div className="legend">
            <span><i style={{ background: "var(--ok)" }} />Ready</span><span><i style={{ background: "var(--warn)" }} />Check</span>
            <span><i style={{ background: "var(--crit)" }} />Internet</span><span><i style={{ border: "1.5px dashed #C2C9D2" }} />Waiting</span>
          </div>
          <button className="btn primary lg" style={{ justifyContent: "center" }} disabled={!exam || exam.state !== "lobby" || ready === 0}
            onClick={() => api.start()}>Start exam · {Math.round((exam?.duration_s ?? 0) / 60)} min</button>
          <div className="sub" style={{ fontSize: 12 }}>Red seats won't receive questions.</div>
        </div>
        <div className="card grid-card">
          <div className="grid-head"><h2>Seats</h2><span className="sub">· pre-flight</span></div>
          <SeatGrid room={room} mode="lobby" onOpen={onOpen} />
        </div>
      </div>
    </section>
  );
}
