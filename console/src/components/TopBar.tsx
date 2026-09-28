import type { ReactNode } from "react";
import type { Page } from "../App";
import type { Room } from "../types";

const STEPS: Page[] = ["setup", "lobby", "live", "results"];
const LABEL: Record<Page, string> = { setup: "Setup", lobby: "Lobby", live: "Live", results: "Results" };

export default function TopBar({ room, page, onPage, children }:
  { room: Room; page: Page; onPage: (p: Page) => void; children?: ReactNode }) {
  const jev = room.mode === "jev";
  return (
    <header className="topbar">
      <div className="logo"><img src="/logo.svg" width={26} height={26} alt="" />Tide</div>
      {room.exam && <div className="exam-name">{room.exam.title}</div>}
      <div className="steps">
        {STEPS.map((s) => <button key={s} className={s === page ? "on" : ""} onClick={() => onPage(s)}>{LABEL[s]}</button>)}
      </div>
      <div className="spacer" />
      {!room.connected && <span className="chip warnchip"><span className="dot" />Reconnecting…</span>}
      <span className={`chip ${jev ? "" : "warnchip"}`}><span className="dot" />{jev ? "Jev live" : "Offline heuristics"}</span>
      {children}
    </header>
  );
}
