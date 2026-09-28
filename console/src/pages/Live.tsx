import { useEffect, useState } from "react";
import { api } from "../api";
import AlertFeed from "../components/AlertFeed";
import SeatGrid from "../components/SeatGrid";
import TopBar from "../components/TopBar";
import { counts, fmtClock, remaining } from "../state";
import type { Page } from "../App";
import type { Room } from "../types";

const SIM = [["ai_site", "ChatGPT closed"], ["jev_ai", "Jev: AI site"], ["internet", "Internet on"],
  ["old_code", "Old code reused"], ["usb", "USB drive"]] as const;

export default function Live({ room, page, onPage, onOpen }:
  { room: Room; page: Page; onPage: (p: Page) => void; onOpen: (id: number) => void }) {
  const [, tick] = useState(0);
  const [filter, setFilter] = useState("all");
  const [menu, setMenu] = useState(false);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(t); }, []);
  const c = counts(room);
  const real = Object.values(room.seats).find((s) => !s.simulated);
  return (
    <section>
      <TopBar room={room} page={page} onPage={onPage}>
        <div className="clock">{fmtClock(remaining(room.exam, room.clockOffset))}</div>
        <button className="btn" onClick={() => api.extend(5)}>+ 5 min</button>
        <button className="btn" onClick={() => { const t = prompt("Notice to all students"); if (t) api.notice(t); }}>Notice</button>
        <div className="menu">
          <button className="btn" onClick={() => setMenu(!menu)}>Simulate</button>
          {menu && <div className="menu-list">{SIM.filter(([k]) => k !== "internet" || room.exam?.internet === "blocked").map(([k, label]) => (
            <button key={k} onClick={() => { setMenu(false); api.simulate(real?.seat_no ?? 7, k); }}>{label} · PC-{String(real?.seat_no ?? 7).padStart(2, "0")}</button>))}</div>}
        </div>
      </TopBar>
      <div className="page">
        <div className="summary">
          {([["ok", "Working", "var(--ok)"], ["warn", "Review", "var(--warn)"], ["crit", "Alert", "var(--crit)"], ["off", "Offline", "var(--off)"]] as const)
            .map(([k, label, color]) => (
              <div key={k} className="card stat"><div className="sw" style={{ background: color }} />
                <div><div className="n">{c[k]}</div><div className="l">{label}</div></div></div>))}
        </div>
        <div className="live">
          <div className="card grid-card">
            <div className="grid-head"><h2>Lab</h2><span className="sub">· {Object.keys(room.seats).length} seats</span>
              <div className="spacer" />
              <div className="filters">{([["all", "All"], ["crit", "Alert"], ["warn", "Review"], ["off", "Offline"]] as const).map(([f, label]) => (
                <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>{label}</button>))}</div>
            </div>
            <SeatGrid room={room} mode="live" filter={filter} onOpen={onOpen} />
          </div>
          <AlertFeed room={room} onOpen={onOpen} />
        </div>
      </div>
    </section>
  );
}
