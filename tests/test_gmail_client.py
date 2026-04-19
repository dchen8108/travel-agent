from __future__ import annotations

from pathlib import Path

import pytest
from google.auth.exceptions import RefreshError

from app.services.gmail_client import GmailAuthorizationRequired, _load_gmail_credentials
from app.settings import Settings


class _ExpiredCreds:
    valid = False
    expired = True
    refresh_token = "refresh-token"

    def refresh(self, _request) -> None:
        raise RefreshError("invalid_grant: Token has been expired or revoked.")


def test_load_gmail_credentials_wraps_revoked_refresh_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.config_local_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_local_dir / "gmail_oauth_client.json").write_text("{}", encoding="utf-8")
    (settings.config_local_dir / "gmail_oauth_token.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.gmail_client.Credentials.from_authorized_user_file",
        lambda *_args, **_kwargs: _ExpiredCreds(),
    )

    with pytest.raises(GmailAuthorizationRequired) as excinfo:
        _load_gmail_credentials(settings)

    assert "authorize_gmail_bookings" in str(excinfo.value)
    assert "expired or been revoked" in str(excinfo.value)
