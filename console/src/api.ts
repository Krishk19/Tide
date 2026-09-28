import type { Exam, Results, SeatDetail, ServerMsg } from "./types";

let token = localStorage.getItem("tide_token") ?? "";
export const auth = {
  get token() { return token; },
  set(t: string) { token = t; localStorage.setItem("tide_token", t); },
  clear() { token = ""; localStorage.removeItem("tide_token"); },
};

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const r = await fetch(path, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body && !isForm ? { "Content-Type": "application/json" } : {}) },
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) { auth.clear(); location.reload(); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail);
  return r.json();
}

export const api = {
  async login(pin: string) {
    const r = await fetch("/api/teacher/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }) });
    if (!r.ok) throw new Error("Wrong PIN");
    auth.set((await r.json()).token);
  },
  catalog: () => req<{ apps: string[]; presets: Record<string, string[]> }>("GET", "/api/teacher/catalog"),
  exam: () => req<{ exam: Exam | null; files: { name: string; set: string }[] }>("GET", "/api/teacher/exam"),
  createExam: (title: string, duration_min: number, apps: string[]) =>
    req<Exam>("POST", "/api/teacher/exams", { title, duration_min, apps }),
  upload: (examId: number, setName: string, file: File) => {
    const f = new FormData(); f.append("set_name", setName); f.append("file", file);
    return req("POST", `/api/teacher/exams/${examId}/files`, f);
  },
  start: () => req<Exam>("POST", "/api/teacher/start"),
  extend: (minutes: number, seat_id?: number) => req("POST", "/api/teacher/extend", { minutes, seat_id }),
  notice: (text: string) => req("POST", "/api/teacher/notice", { text }),
  warn: (seatId: number) => req("POST", `/api/teacher/seats/${seatId}/warn`, {}),
  forceSubmit: (seatId: number) => req("POST", `/api/teacher/seats/${seatId}/force-submit`),
  seat: (seatId: number) => req<SeatDetail>("GET", `/api/teacher/seats/${seatId}`),
  review: (flagId: number, status: "dismissed" | "confirmed") => req("PATCH", `/api/teacher/flags/${flagId}`, { status }),
  results: () => req<Results>("GET", "/api/teacher/results"),
  simulate: (seat_no: number, kind: string) => req("POST", "/api/teacher/simulate", { seat_no, kind }),
  shotUrl: (flagId: number) => `/api/teacher/shots/${flagId}?token=${token}`,
  csvUrl: () => `/api/teacher/results.csv?token=${token}`,
  submissionUrl: (seatId: number) => `/api/teacher/submissions/${seatId}?token=${token}`,
};

export function connect(onMsg: (m: ServerMsg) => void): () => void {
  let ws: WebSocket | null = null;
  let stopped = false;
  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/console?token=${token}`);
    ws.onmessage = (e) => onMsg(JSON.parse(e.data));
    ws.onclose = () => { onMsg({ t: "connected", value: false }); if (!stopped) setTimeout(open, 1500); };
  };
  open();
  return () => { stopped = true; ws?.close(); };
}
