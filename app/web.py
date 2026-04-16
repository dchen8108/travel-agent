from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from fastapi.responses import RedirectResponse
from app.settings import Settings, get_settings
from app.storage.repository import Repository


def _canonical_dashboard_target(path: str, query: str = "") -> str:
    dashboard_targets = {
        "/trips": ("", "all-travel"),
        "/trackers": ("", "all-travel"),
        "/bookings": ("", "needs-linking"),
    }
    if path not in dashboard_targets:
        return f"{path}{f'?{query}' if query else ''}"
    canonical_path, fragment = dashboard_targets[path]
    query = urlencode(
        [(key, value) for key, value in parse_qsl(query, keep_blank_values=True) if key != "q"],
        doseq=True,
    )
    target = canonical_path or "/"
    if query:
        target = f"{target}?{query}"
    if fragment:
        target = f"{target}#{fragment}"
    return target


def get_repository(request: Request) -> Repository:
    settings: Settings = getattr(request.app.state, "settings", get_settings())
    repository = Repository(settings)
    repository.ensure_data_dir()
    return repository


def with_message(url: str, message: str, *, message_kind: str = "success") -> str:
    parsed = urlsplit(url)
    params = parse_qsl(parsed.query, keep_blank_values=True)
    params.append(("message", message))
    if message_kind != "success":
        params.append(("message_kind", message_kind))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(params, doseq=True), parsed.fragment))


def redirect_with_message(
    url: str,
    message: str,
    *,
    message_kind: str = "success",
    status_code: int = 303,
) -> RedirectResponse:
    return RedirectResponse(url=with_message(url, message, message_kind=message_kind), status_code=status_code)


def redirect_back(
    request: Request,
    *,
    fallback_url: str,
    message: str | None = None,
    message_kind: str = "success",
    status_code: int = 303,
) -> RedirectResponse:
    target = back_url(request, fallback_url=fallback_url)
    if target != fallback_url:
        if message:
            target = with_message(target, message, message_kind=message_kind)
        return RedirectResponse(url=target, status_code=status_code)
    if message:
        return redirect_with_message(fallback_url, message, message_kind=message_kind, status_code=status_code)
    return RedirectResponse(url=fallback_url, status_code=status_code)


def back_url(request: Request, *, fallback_url: str) -> str:
    referer = request.headers.get("referer", "")
    if referer:
        parsed = urlsplit(referer)
        same_origin = (
            (not parsed.scheme and not parsed.netloc)
            or (
                parsed.scheme == request.url.scheme
                and parsed.netloc == request.url.netloc
            )
        )
        if same_origin and parsed.path.startswith("/"):
            return _canonical_dashboard_target(parsed.path, parsed.query)
    return fallback_url
