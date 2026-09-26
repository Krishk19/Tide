import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Tide Secure Lab Assessment API"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "tide-insecure-lab-dev-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours for lab sessions
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./tide.db")
    JUDGE0_URL: str = os.getenv("JUDGE0_URL", "http://localhost:2358")

    class Config:
        case_sensitive = True

settings = Settings()
