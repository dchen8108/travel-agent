from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from app.storage.repository import Repository


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )


@pytest.fixture
def repository(settings: Settings) -> Repository:
    repository = Repository(settings)
    repository.ensure_data_dir()
    return repository


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    return TestClient(app)
