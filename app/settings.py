from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_root: Path = Path(__file__).resolve().parents[1]
    data_dir: Path = project_root / "data"
    config_dir: Path = project_root / "config"
    templates_dir: Path = project_root / "app" / "templates"
    static_dir: Path = project_root / "app" / "static"
    timezone: str = "America/Los_Angeles"
    future_weeks: int = 12

    @property
    def config_local_dir(self) -> Path:
        return self.config_dir / "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
