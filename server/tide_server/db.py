from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine

from tide_server import models  # noqa: F401  (registers tables)


def make_engine(data_dir: Path) -> Engine:
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{data_dir / 'tide.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine
