import asyncio
import socket
import threading
import time

import httpx
import uvicorn

from tide_agent.fake import FakePlatform
from tide_agent.main import AgentApp, AgentConfig
from tide_agent.ui.headless import HeadlessUI


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def test_fake_student_end_to_end(tmp_path):
    from tide_server.app import create_app
    from tide_server.config import Settings
    port = free_port()
    settings = Settings(_env_file=None, data_dir=tmp_path / "srv", openrouter_api_key="", demo=True,
                        background_tasks=False, console_dir=tmp_path / "none", port=port)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient(base_url=base) as http:
        for _ in range(50):
            try:
                tok = (await http.post("/api/teacher/login", json={"pin": "2468"})).json()["token"]
                break
            except httpx.HTTPError:
                await asyncio.sleep(0.1)
        H = {"Authorization": f"Bearer {tok}"}
        code = (await http.get("/api/teacher/exam", headers=H)).json()["exam"]["join_code"]

        lines = []
        fake = FakePlatform(tmp_path / "home")
        cfg = AgentConfig(server=f"127.0.0.1:{port}", exam_root=tmp_path / "Exam", ext_dir=fake.ext_dir,
                          state_dir=tmp_path / "state", roots=[fake.old_dir])
        app = AgentApp(fake, HeadlessUI(out=lines.append), cfg)
        await app.boot()
        assert (await app.join(code, "22bcs107", 7))["ok"]
        for _ in range(100):
            if any(l.startswith("[preflight] ok:Offline") for l in lines):
                break
            await asyncio.sleep(0.05)
        await http.post("/api/teacher/start", headers=H)
        for _ in range(100):
            if any(l.startswith("[start]") for l in lines):
                break
            await asyncio.sleep(0.05)
        assert (tmp_path / "Exam" / "22BCS107" / "questions.txt").exists()

        fake.command("ai")
        await asyncio.sleep(1.2)
        assert any("ChatGPT — closed" in l for l in lines)
        seats = (await http.get("/api/teacher/results", headers=H)).json()["rows"]
        me = next(r for r in seats if r["seat_no"] == 7)
        assert any(f["title"] == "ChatGPT — closed" for f in me["flags"])

        await app.engine.submit(auto=False)
        assert any(l.startswith("[done]") for l in lines)
    server.should_exit = True
    time.sleep(0.2)
