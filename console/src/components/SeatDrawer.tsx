import { useEffect, useState } from "react";
import { api } from "../api";
import type { Room, SeatDetail, TimelineItem } from "../types";

const t = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const DOT = { critical: "crit", high: "crit", medium: "warn", info: "info" } as const;
const STATUS = { ok: "Working", warn: "Review", crit: "Alert", off: "Offline", wait: "Waiting", done: "Submitted" } as const;

function Item({ i, reload }: { i: TimelineItem; reload: () => void }) {
  if (i.type === "event")
    return <div className={`ev ${i.kind === "start" || i.kind === "joined" ? "brand" : "info"}`}><div className="h"><time>{t(i.ts)}</time><span className="x">{i.text}</span></div></div>;
  const acted = i.action === "close_tab" || i.action === "kill";
  return (
    <div className={`ev ${DOT[i.severity]}`}>
      <div className="h"><time>{t(i.ts)}</time><span className="x">{i.title}</span></div>
      <div className="card">
        {i.has_shot && <div className="shot"><img src={api.shotUrl(i.id)} alt="screenshot" /></div>}
        {i.source === "jev" && i.confidence != null && (
          <div className="conf"><span className="src jev">Jev</span>{i.label}
            <div className="meter"><i style={{ width: `${i.confidence * 100}%` }} /></div><b>{i.confidence.toFixed(2)}</b></div>)}
        <div className="fl-act">
          {acted ? <span className="acted">Auto-closed</span> : <span className="src rule">{i.source === "jev" ? "Jev" : "Rule"}</span>}
          <span className="spacer" />
          {i.status === "open" ? <>
            <button className="btn" onClick={() => api.review(i.id, "dismissed").then(reload)}>Dismiss</button>
            <button className="btn danger" onClick={() => api.review(i.id, "confirmed").then(reload)}>Confirm</button>
          </> : <span className="sub">{i.status}</span>}
        </div>
      </div>
    </div>
  );
}

function Growth({ d }: { d: SeatDetail }) {
  const g = d.growth;
  if (g.length < 2) return <div className="sub">Not enough snapshots yet.</div>;
  const t0 = g[0].ts, t1 = g[g.length - 1].ts || t0 + 1, max = Math.max(...g.map((p) => p.lines), 1);
  const x = (ts: number) => ((ts - t0) / Math.max(1, t1 - t0)) * 500;
  const y = (n: number) => 160 - (n / max) * 140;
  const pts = g.map((p) => `${x(p.ts)},${y(p.lines)}`).join(" ");
  const bursts = d.timeline.filter((i) => i.type === "flag" && i.kind === "code_burst");
  return (
    <svg viewBox="0 0 500 170" preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke="#0B7A83" strokeWidth={2.5} />
      {bursts.map((b) => <line key={b.id} x1={x(b.ts)} x2={x(b.ts)} y1={10} y2={165} stroke="#DC2626" strokeDasharray="4 4" />)}
    </svg>
  );
}

export default function SeatDrawer({ seatId, room, onClose }: { seatId: number | null; room: Room; onClose: () => void }) {
  const [d, setD] = useState<SeatDetail | null>(null);
  const [tab, setTab] = useState<"tl" | "code">("tl");
  const version = seatId ? Object.values(room.flags).filter((f) => f.seat_id === seatId).map((f) => `${f.id}${f.status}${f.has_shot}`).join()
    + (room.lastEvent?.seat_id === seatId ? room.lastEvent.id : "") : "";
  const reload = () => { if (seatId) api.seat(seatId).then(setD); };
  useEffect(() => { setD(null); setTab("tl"); }, [seatId]);
  useEffect(reload, [seatId, version]);
  const s = d?.seat;
  return (
    <>
      <div className={`scrim ${seatId ? "on" : ""}`} onClick={onClose} />
      <aside className={`drawer ${seatId ? "on" : ""}`}>
        {s && <>
          <div className="dr-hd">
            <div className="dr-title"><span className="big">PC-{String(s.seat_no).padStart(2, "0")}</span>
              <span className={`status-pill ${s.status === "off" ? "warn" : s.status}`}>{STATUS[s.status]}</span>
              <div className="spacer" /><button className="btn ghost" onClick={onClose}>✕</button></div>
            <div className="dr-meta"><span className="mono">{s.roll}</span><span>Set {s.set ?? "—"}</span><span>Now: {s.fg_app || "—"}</span></div>
            <div className="dr-actions">
              <button className="btn" onClick={() => api.warn(s.id)}>Warn</button>
              <button className="btn" onClick={() => api.extend(5, s.id)}>+ 5 min</button>
              <button className="btn danger" onClick={() => confirm("Force submit this seat?") && api.forceSubmit(s.id)}>Force submit</button>
            </div>
          </div>
          <div className="tabs">
            <button className={tab === "tl" ? "on" : ""} onClick={() => setTab("tl")}>Timeline</button>
            <button className={tab === "code" ? "on" : ""} onClick={() => setTab("code")}>Code</button>
          </div>
          <div className="dr-body">
            {tab === "tl" ? <div className="tl">{d!.timeline.map((i) => <Item key={`${i.type}${i.id}`} i={i} reload={reload} />)}</div> : <>
              <div className="card chart"><h2>Lines in exam folder</h2><Growth d={d!} /></div>
              <div className="files">{d!.files.map((f) => <div key={f.path} className="file">{f.path}<span className="spacer" /><span className="sub">{f.lines} lines</span></div>)}</div>
            </>}
          </div>
        </>}
      </aside>
    </>
  );
}
