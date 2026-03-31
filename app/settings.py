from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    project_root: Path = Path(__file__).resolve().parents[1]
    data_dir: Path = project_root / "data"
    imported_email_dir: Path = data_dir / "imported_emails"
    templates_dir: Path = project_root / "app" / "templates"
    static_dir: Path = project_root / "app" / "static"
    timezone: str = "America/Los_Angeles"
    default_lookahead_weeks: int = 8
    default_rebook_alert_threshold: int = 20


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
