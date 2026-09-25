from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ITADB_", env_file=".env", extra="ignore")
    data_dir: Path = Path("data")
    cors_origins: list[str] = ["http://localhost:5173"]
    root_path: str = ""
    serving_dir: Path = Path("data/serving")
    duckdb_memory_mb: int = Field(default=256, ge=64, le=65536)
    duckdb_threads: int = Field(default=2, ge=1, le=32)
    serving_concurrency: int = Field(default=4, ge=1, le=32)
    serving_timeout_seconds: float = Field(default=5, gt=0, le=60)
