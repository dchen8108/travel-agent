from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import base64
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from selectolax.parser import HTMLParser

from app.settings import Settings


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailAuthorizationRequired(RuntimeError):
    pass


@dataclass
class GmailMessage:
    gmail_message_id: str
    gmail_thread_id: str
    gmail_history_id: str
    from_address: str
    subject: str
    received_at: datetime
    body_text: str


def gmail_oauth_client_path(settings: Settings) -> Path:
    return settings.config_local_dir / "gmail_oauth_client.json"


def gmail_token_path(settings: Settings) -> Path:
    return settings.config_local_dir / "gmail_oauth_token.json"


def gmail_auth_status(settings: Settings) -> dict[str, object]:
    client_path = gmail_oauth_client_path(settings)
    token_path = gmail_token_path(settings)
    return {
        "client_config_present": client_path.exists(),
        "token_present": token_path.exists(),
        "ready": client_path.exists() and token_path.exists(),
        "authorize_command": "uv run python -m app.jobs.authorize_gmail_bookings",
    }


def authorize_gmail(settings: Settings) -> Path:
    client_path = gmail_oauth_client_path(settings)
    if not client_path.exists():
        raise GmailAuthorizationRequired(
            f"Missing Gmail OAuth client config at {client_path}."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path = gmail_token_path(settings)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return token_path


def build_gmail_service(settings: Settings):
    creds = _load_gmail_credentials(settings)
    if creds is None:
        raise GmailAuthorizationRequired(
            "Gmail authorization is not set up yet. Run `uv run python -m app.jobs.authorize_gmail_bookings`."
        )
    return build("gmail", "v1", credentials=creds)


def list_recent_inbox_message_ids(
    service,
    *,
    label_ids: list[str],
    max_results: int,
) -> list[str]:
    response = (
        service.users()
        .messages()
        .list(userId="me", labelIds=label_ids, maxResults=max_results)
        .execute()
    )
    return [str(item["id"]) for item in response.get("messages", [])]


def fetch_gmail_message(service, message_id: str) -> GmailMessage:
    payload = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    headers = {
        header.get("name", "").lower(): header.get("value", "")
        for header in payload.get("payload", {}).get("headers", [])
    }
    body_text = _extract_message_body(payload.get("payload", {}))
    received_at = _parse_received_at(headers, payload)
    return GmailMessage(
        gmail_message_id=str(payload.get("id", "")),
        gmail_thread_id=str(payload.get("threadId", "")),
        gmail_history_id=str(payload.get("historyId", "")),
        from_address=headers.get("from", ""),
        subject=headers.get("subject", ""),
        received_at=received_at,
        body_text=body_text,
    )


def _load_gmail_credentials(settings: Settings) -> Credentials | None:
    client_path = gmail_oauth_client_path(settings)
    token_path = gmail_token_path(settings)
    if not client_path.exists():
        return None
    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds
    return None


def _extract_message_body(payload: dict[str, Any]) -> str:
    text_parts: list[str] = []
    html_parts: list[str] = []
    _collect_parts(payload, text_parts, html_parts)
    if text_parts:
        return "\n\n".join(part for part in text_parts if part).strip()
    html_text = "\n\n".join(part for part in html_parts if part).strip()
    if not html_text:
        return ""
    parser = HTMLParser(html_text)
    return parser.body.text(separator="\n") if parser.body else parser.text(separator="\n")


def _collect_parts(part: dict[str, Any], text_parts: list[str], html_parts: list[str]) -> None:
    mime_type = str(part.get("mimeType", "")).lower()
    body = part.get("body", {}) or {}
    data = body.get("data")
    if data:
        decoded = _decode_base64_url(data)
        if mime_type == "text/plain":
            text_parts.append(decoded)
        elif mime_type == "text/html":
            html_parts.append(decoded)
    for child in part.get("parts", []) or []:
        _collect_parts(child, text_parts, html_parts)


def _decode_base64_url(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(data + padding)
    return raw.decode("utf-8", errors="replace")


def _parse_received_at(headers: dict[str, str], payload: dict[str, Any]) -> datetime:
    date_header = headers.get("date", "")
    if date_header:
        try:
            parsed = parsedate_to_datetime(date_header)
            if parsed is not None:
                return parsed.astimezone()
        except (TypeError, ValueError, IndexError):
            pass
    internal_ms = str(payload.get("internalDate", "")).strip()
    if internal_ms.isdigit():
        return datetime.fromtimestamp(int(internal_ms) / 1000).astimezone()
    return datetime.now().astimezone()


__all__ = [
    "GmailAuthorizationRequired",
    "GmailMessage",
    "authorize_gmail",
    "build_gmail_service",
    "fetch_gmail_message",
    "gmail_auth_status",
    "gmail_oauth_client_path",
    "gmail_token_path",
    "list_recent_inbox_message_ids",
]

