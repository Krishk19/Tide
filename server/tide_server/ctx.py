from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import Request
from sqlalchemy import Engine
from sqlmodel import Session

from tide_server.config import Settings
from tide_server.hub import Hub

if TYPE_CHECKING:
    from tide_server.classify.pipeline import Pipeline
    from tide_server.ingest import Ingest


@dataclass
class Ctx:
    settings: Settings
    engine: Engine
    hub: Hub
    teacher_tokens: set[str] = field(default_factory=set)
    pipeline: "Pipeline | None" = None
    ingest: "Ingest | None" = None
    ended_seats: set[int] = field(default_factory=set)
    extras: dict[str, Any] = field(default_factory=dict)

    def db(self) -> Session:
        return Session(self.engine, expire_on_commit=False)


def get_ctx(request: Request) -> Ctx:
    return request.app.state.ctx
