import { openAlerts } from "../state";
import type { Room } from "../types";

const SEV_CLASS = { critical: "crit", high: "crit", medium: "warn", info: "off" } as const;
const time = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export default function AlertFeed({ room, onOpen }: { room: Room; onOpen: (seatId: number) => void }) {
  const alerts = openAlerts(room);
  return (
    <div className="card feed">
      <div className="feed-hd"><h2>Alerts</h2><span className="sub">· {alerts.length} open</span></div>
      <div className="feed-list">
        {alerts.map((a) => (
          <div key={a.id} className={`alert ${a.kind === "agent_offline" ? "off" : SEV_CLASS[a.severity]}`} onClick={() => onOpen(a.seat_id)}>
            <div className="sico">{String(a.seat_no).padStart(2, "0")}</div>
            <div>
              <div className="t">{a.title}</div>
              <div className="m">PC-{String(a.seat_no).padStart(2, "0")}
                {a.source === "jev" && <span className="src jev">Jev {a.confidence?.toFixed(2)}</span>}
                {a.source === "rule" && <span className="src rule">Rule</span>}
                {(a.action === "close_tab" || a.action === "kill") && <span className="acted">Auto-closed</span>}
              </div>
            </div>
            <time>{time(a.ts)}</time>
          </div>
        ))}
        {alerts.length === 0 && <div className="sub" style={{ padding: 18 }}>All quiet.</div>}
      </div>
    </div>
  );
}
