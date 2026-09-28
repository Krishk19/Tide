import { useEffect, useState } from "react";
import { api } from "../api";
import TopBar from "../components/TopBar";
import type { Page } from "../App";
import type { Results as R, Room } from "../types";

export default function Results({ room, page, onPage, onOpen }:
  { room: Room; page: Page; onPage: (p: Page) => void; onOpen: (id: number) => void }) {
  const [r, setR] = useState<R | null>(null);
  useEffect(() => { api.results().then(setR); }, [room.flags]);
  const submitted = r?.rows.filter((x) => x.submitted_at).length ?? 0;
  const sev = (s: string) => (s === "medium" ? "warn" : "crit");
  return (
    <section>
      <TopBar room={room} page={page} onPage={onPage}>
        <span className="chip">{submitted}/{r?.rows.length ?? 0} submitted</span>
        <a className="btn primary" href={api.csvUrl()}>Export CSV</a>
      </TopBar>
      <div className="page results">
        <div className="card" style={{ overflow: "hidden" }}>
          <table>
            <thead><tr><th>Seat</th><th>Roll</th><th>Set</th><th>Submitted</th><th>Flags</th><th>Max match</th><th /></tr></thead>
            <tbody>{r?.rows.map((x) => (
              <tr key={x.seat_id} onClick={() => onOpen(x.seat_id)} style={{ cursor: "pointer" }}>
                <td><b>PC-{String(x.seat_no).padStart(2, "0")}</b></td><td className="mono">{x.roll}</td><td>{x.set ?? "—"}</td>
                <td>{x.submitted_at ? new Date(x.submitted_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                <td><div className="fchips">{x.flags.length ? x.flags.map((f, i) => <span key={i} className={`fc ${sev(f.severity)}`}>{f.title}</span>) : <span className="sub">—</span>}</div></td>
                <td>{x.max_match != null ? <b style={{ color: x.max_match >= 80 ? "var(--crit)" : undefined }}>{x.max_match}%</b> : <span className="sub">—</span>}</td>
                <td>{x.submitted_at && <a className="btn ghost" onClick={(e) => e.stopPropagation()} href={api.submissionUrl(x.seat_id)}>Files</a>}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="card sim"><h2>Similar submissions</h2>
            {r?.pairs.map((p, i) => (
              <div key={i} className="pair"><b>PC-{String(p.a).padStart(2, "0")}</b>↔
                {p.b != null ? <b>PC-{String(p.b).padStart(2, "0")}</b> : <span className="mono" style={{ fontSize: 12 }}>{p.b_path}</span>}
                <span className={`pct ${p.pct >= 80 ? "hi" : ""}`}>{p.pct}%</span></div>))}
            {!r?.pairs.length && <span className="sub">None above 40%.</span>}
          </div>
          <div className="card sim"><h2>Flags this exam</h2>
            {r && Object.entries(r.flag_counts).map(([k, n]) => <div key={k} className="pair">{k}<span className="pct">{n}</span></div>)}
          </div>
        </div>
      </div>
    </section>
  );
}
