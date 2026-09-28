import { useState } from "react";
import { api } from "../api";

export default function Login({ onDone }: { onDone: () => void }) {
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  return (
    <form className="card login" onSubmit={async (e) => {
      e.preventDefault();
      try { await api.login(pin); onDone(); } catch { setErr("Wrong PIN"); }
    }}>
      <div className="logo"><img src="/logo.svg" width={26} height={26} alt="" />Tide</div>
      <label className="lbl">Teacher PIN</label>
      <input className="input mono" autoFocus inputMode="numeric" value={pin} onChange={(e) => setPin(e.target.value)} />
      {err && <div style={{ color: "var(--crit)" }}>{err}</div>}
      <button className="btn primary lg">Open console</button>
    </form>
  );
}
