import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tide_server import monitor
from tide_server.api import agent, console, teacher
from tide_server.classify.jev import JevClassifier
from tide_server.classify.pipeline import Pipeline
from tide_server.config import Settings
from tide_server.ctx import Ctx
from tide_server.db import make_engine
from tide_server.discovery import start_discovery
from tide_server.hub import Hub
from tide_server.ingest import Ingest
from tide_server.simulate import SimRoom, bootstrap_demo, run_sim


def build_pipeline(settings: Settings) -> Pipeline:
    if not settings.openrouter_api_key:
        return Pipeline(None)
    return Pipeline(JevClassifier(settings.jev_url, settings.openrouter_api_key, settings.jev_model))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    ctx = Ctx(settings=settings, engine=make_engine(settings.data_dir), hub=Hub())
    ctx.pipeline = build_pipeline(settings)
    ctx.ingest = Ingest(ctx)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks: list[asyncio.Task] = []
        transport = None
        if settings.demo:
            ctx.extras["exam_id"] = bootstrap_demo(ctx)
        if settings.background_tasks:
            tasks.append(asyncio.create_task(monitor.run(ctx)))
            if settings.demo:
                tasks.append(asyncio.create_task(run_sim(SimRoom(ctx, ctx.extras["exam_id"]))))
            try:
                transport = await start_discovery(settings.host, settings.discovery_port, settings.port)
            except OSError as e:
                print(f"[discovery] disabled: {e}")
        yield
        for t in tasks:
            t.cancel()
        if transport:
            transport.close()

    app = FastAPI(title="Tide", lifespan=lifespan)
    app.state.ctx = ctx
    app.include_router(teacher.router)
    app.include_router(agent.router)
    app.include_router(console.router)
    if settings.console_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.console_dir, html=True), name="console")
    return app
