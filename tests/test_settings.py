from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import Settings


def test_settings_reject_unknown_fields(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Settings(
            data_dir=tmp_path / "data",
            templates_dir=Path("app/templates"),
            static_dir=Path("app/static"),
            imported_email_dir=tmp_path / "data" / "imported_emails",
        )
