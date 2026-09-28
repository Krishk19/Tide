from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TIDE_", env_file=(REPO_ROOT / ".env", REPO_ROOT / ".env.local", ".env", ".env.local"),
                                      extra="ignore", populate_by_name=True)

    data_dir: Path = Path("tide-data")
    host: str = "0.0.0.0"
    port: int = 8765
    discovery_port: int = 47800
    teacher_pin: str = "2468"
    heartbeat_timeout_s: float = 10.0
    auto_act_min: float = 0.90
    demo: bool = False
    background_tasks: bool = True
    console_dir: Path = REPO_ROOT / "console" / "dist"
    openrouter_api_key: str = Field(default="", validation_alias=AliasChoices(
        "OPENROUTER_API_KEY", "openrouter_api_key"))
    jev_model: str = "~typesafe/jev-latest"
    jev_url: str = "https://openrouter.ai/api/alpha/decisions"
