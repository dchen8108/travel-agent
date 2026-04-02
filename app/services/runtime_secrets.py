from __future__ import annotations

import os
from pathlib import Path

from app.settings import Settings


def local_secret_path(settings: Settings, name: str) -> Path:
    return settings.config_local_dir / name


def load_secret_value(settings: Settings, *, env_var: str, local_filename: str) -> str:
    value = os.getenv(env_var, "").strip()
    if value:
        return value
    path = local_secret_path(settings, local_filename)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def openai_api_key(settings: Settings) -> str:
    return load_secret_value(
        settings,
        env_var="OPENAI_API_KEY",
        local_filename="openai_api_key.txt",
    )


def ensure_local_secret_from_env(
    settings: Settings,
    *,
    env_var: str,
    local_filename: str,
) -> Path | None:
    value = os.getenv(env_var, "").strip()
    if not value:
        return None
    path = local_secret_path(settings, local_filename)
    if path.exists() and path.read_text(encoding="utf-8").strip():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")
    path.chmod(0o600)
    return path
