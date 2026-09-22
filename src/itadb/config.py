from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ITADB_", env_file=".env", extra="ignore")
    database_url: str = "postgresql://itadb_reader:local_reader_only@localhost:5432/itadb"
    admin_database_url: str = "postgresql://itadb:local_dev_only@localhost:5432/itadb"
    data_dir: Path = Path("data")
    cors_origins: list[str] = ["http://localhost:5173"]
    pool_min_size: int = 1
    pool_max_size: int = 8
    root_path: str = ""
