import pytest
from fastapi.testclient import TestClient

from tide_common.policy import PRESETS
from tide_server.config import Settings
from tide_server.hub import Hub


class RecordingHub(Hub):
    def __init__(self):
        super().__init__()
        self.console_msgs: list[dict] = []
        self.agent_msgs: list[tuple[int, dict]] = []

    async def to_console(self, message):
        self.console_msgs.append(message)
        await super().to_console(message)

    async def to_agent(self, seat_id, message):
        self.agent_msgs.append((seat_id, message))
        return await super().to_agent(seat_id, message)


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path / "data", openrouter_api_key="",
                    background_tasks=False, console_dir=tmp_path / "no-console")


@pytest.fixture
def app(settings):
    from tide_server.app import create_app
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def ctx(app):
    return app.state.ctx


@pytest.fixture
def hub(ctx):
    ctx.hub = RecordingHub()
    return ctx.hub


@pytest.fixture
def teacher(client):
    token = client.post("/api/teacher/login", json={"pin": "2468"}).json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def exam(ctx):
    from tide_server.exam_service import create_exam
    with ctx.db() as db:
        return create_exam(db, "CN Lab Test 3", 90 * 60, list(PRESETS["networking"]))


@pytest.fixture
def blocked_exam(ctx):
    from tide_server.exam_service import create_exam
    with ctx.db() as db:
        return create_exam(db, "Offline Lab", 90 * 60, list(PRESETS["networking"]), internet="blocked")


@pytest.fixture
def paired(ctx, exam):
    from tide_server.exam_service import pair_seat
    with ctx.db() as db:
        seat, token = pair_seat(db, exam.join_code, "22bcs107", 7, "LAB3-PC07")
    return seat, token
