import { useEffect, useReducer, useState } from "react";
import { auth, connect } from "./api";
import { emptyRoom, reduce } from "./state";
import Login from "./pages/Login";
import Setup from "./pages/Setup";
import Lobby from "./pages/Lobby";
import Live from "./pages/Live";
import Results from "./pages/Results";
import SeatDrawer from "./components/SeatDrawer";

export type Page = "setup" | "lobby" | "live" | "results";

function pageFor(state?: string): Page {
  return state === "lobby" ? "lobby" : state === "live" ? "live" : state === "ended" ? "results" : "setup";
}

export default function App() {
  const [authed, setAuthed] = useState(Boolean(auth.token));
  const [room, dispatch] = useReducer(reduce, emptyRoom);
  const [page, setPage] = useState<Page | null>(null);
  const [drawer, setDrawer] = useState<number | null>(null);

  useEffect(() => (authed ? connect(dispatch) : undefined), [authed]);
  useEffect(() => { if (room.connected && page === null) setPage(pageFor(room.exam?.state)); }, [room.connected, room.exam, page]);
  useEffect(() => { if (room.exam?.state === "live" && page === "lobby") setPage("live"); }, [room.exam?.state, page]);

  if (!authed) return <Login onDone={() => setAuthed(true)} />;
  const p = page ?? "setup";
  const common = { room, page: p, onPage: setPage, onOpen: setDrawer };
  return (
    <>
      {p === "setup" && <Setup {...common} onCreated={() => setPage("lobby")} />}
      {p === "lobby" && <Lobby {...common} />}
      {p === "live" && <Live {...common} />}
      {p === "results" && <Results {...common} />}
      <SeatDrawer seatId={drawer} room={room} onClose={() => setDrawer(null)} />
    </>
  );
}
