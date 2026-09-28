import { useEffect, useState } from "react";
import { api } from "../api";
import TopBar from "../components/TopBar";
import type { Page } from "../App";
import type { Room } from "../types";

const ICON: Record<string, [string, string]> = {
  "VS Code": ["#0078D4", "VS"], CodeBlocks: ["#C2410C", "CB"], Terminal: ["#334155", ">_"], Explorer: ["#F5B400", "E"],
  Wireshark: ["#1679A7", "W"], VMware: ["#6D28D9", "VM"], Notepad: ["#0EA5E9", "N"],
};

export default function Setup({ room, page, onPage, onCreated }:
  { room: Room; page: Page; onPage: (p: Page) => void; onCreated: () => void; onOpen: (id: number) => void }) {
  const [title, setTitle] = useState("CN Lab Test");
  const [minutes, setMinutes] = useState(90);
  const [catalog, setCatalog] = useState<{ apps: string[]; presets: Record<string, string[]> } | null>(null);
  const [preset, setPreset] = useState("networking");
  const [apps, setApps] = useState<Set<string>>(new Set());
  const [files, setFiles] = useState<{ A: File[]; B: File[] }>({ A: [], B: [] });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { api.catalog().then((c) => { setCatalog(c); setApps(new Set(c.presets.networking)); }); }, []);
  const choose = (p: string) => { setPreset(p); if (catalog?.presets[p]) setApps(new Set(catalog.presets[p])); };
  const toggle = (a: string) => { const n = new Set(apps); n.has(a) ? n.delete(a) : n.add(a); setApps(n); setPreset("custom"); };

  async function create() {
    setBusy(true); setErr("");
    try {
      const exam = await api.createExam(title, minutes, [...apps]);
      for (const s of ["A", "B"] as const) for (const f of files[s]) await api.upload(exam.id, s, f);
      onCreated();
    } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  }

  return (
    <section>
      <TopBar room={room} page={page} onPage={onPage} />
      <div className="card setup">
        <h1>New lab test</h1>
        <div className="sub">Questions stay here until you press Start.</div>
        <div className="row">
          <div><label className="lbl">Title</label><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
          <div><label className="lbl">Duration</label>
            <div className="stepper"><button onClick={() => setMinutes(Math.max(5, minutes - 5))}>−</button>
              <div>{minutes} min</div><button onClick={() => setMinutes(Math.min(300, minutes + 5))}>+</button></div></div>
        </div>
        <hr className="sep" />
        <label className="lbl">Question sets</label>
        <div className="sets">
          {(["A", "B"] as const).map((s) => (
            <label key={s} className="drop">
              <div className="hd"><h2>Set {s}</h2><span className="tag">{s === "A" ? "Odd seats · 1, 3, 5…" : "Even seats · 2, 4, 6…"}</span></div>
              {files[s].map((f) => <div key={f.name} className="file">{f.name}</div>)}
              <span className="addfile">+ Add files</span>
              <input type="file" multiple hidden onChange={(e) => setFiles({ ...files, [s]: [...files[s], ...Array.from(e.target.files ?? [])] })} />
            </label>
          ))}
        </div>
        <hr className="sep" />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <label className="lbl" style={{ margin: 0 }}>Allowed apps</label>
          <div className="seg">{["networking", "programming", "custom"].map((p) =>
            <button key={p} className={preset === p ? "on" : ""} onClick={() => choose(p)}>{p[0].toUpperCase() + p.slice(1)}</button>)}</div>
        </div>
        <div className="apps">{catalog?.apps.map((a) => (
          <span key={a} className={`app ${apps.has(a) ? "" : "off"}`} onClick={() => toggle(a)}>
            <span className="ic" style={{ background: ICON[a]?.[0] ?? "#64748B" }}>{ICON[a]?.[1] ?? a[0]}</span>{a}</span>))}</div>
        <div className="blocked"><div><b>Always blocked:</b> AI assistants, messengers, email, remote desktop, internet.{" "}
          <span style={{ opacity: 0.7 }}>Browsers only for local files. Unknown apps are checked by Jev.</span></div></div>
        {err && <div style={{ color: "var(--crit)", marginTop: 12 }}>{err}</div>}
        <div className="setup-foot"><button className="btn primary lg" disabled={busy || !title} onClick={create}>
          {busy ? "Creating…" : "Create & open lobby"}</button></div>
      </div>
    </section>
  );
}
