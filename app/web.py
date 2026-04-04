from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.catalog import airline_display, airline_label, airport_display, airport_label
from app.money import format_money
from app.route_options import day_offset_label, route_option_summary
from app.services.dashboard import (
    active_booking_count_for_instance,
    best_tracker,
    bookings_for_instance,
    booking_for_instance,
    group_for_instance,
    group_for_trip,
    groups_for_instance,
    groups_for_rule,
    groups_for_trip,
    rebook_savings,
    recurring_rule_for_instance,
    trip_for_instance,
    trip_lifecycle_status_label,
    trip_lifecycle_status_tone,
    trip_monitoring_status_label,
    trip_recommended_action,
    trip_status_detail,
)
from app.settings import Settings, get_settings
from app.storage.repository import Repository

templates = Jinja2Templates(directory=str(get_settings().templates_dir))


def _canonical_dashboard_target(path: str, query: str = "") -> str:
    dashboard_targets = {
        "/trips": ("", "all-travel"),
        "/trackers": ("", "all-travel"),
        "/bookings": ("", "needs-linking"),
        "/resolve": ("", "needs-linking"),
    }
    if path not in dashboard_targets:
        return f"{path}{f'?{query}' if query else ''}"
    canonical_path, fragment = dashboard_targets[path]
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


def get_templates(request: Request) -> Jinja2Templates:
    return getattr(request.app.state, "templates", templates)


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
            target = _canonical_dashboard_target(parsed.path, parsed.query)
            if message:
                target = with_message(target, message, message_kind=message_kind)
            return RedirectResponse(url=target, status_code=status_code)
    if message:
        return redirect_with_message(fallback_url, message, message_kind=message_kind, status_code=status_code)
    return RedirectResponse(url=fallback_url, status_code=status_code)


def base_context(request: Request, **extra: object) -> dict[str, object]:
    context: dict[str, object] = {
        "request": request,
        "message": request.query_params.get("message", ""),
        "message_kind": request.query_params.get("message_kind", "success"),
        "asset_version": getattr(request.app.state, "asset_version", "1"),
        "page": extra.pop("page", ""),
        "airport_label": airport_label,
        "airport_display": airport_display,
        "airline_label": airline_label,
        "airline_display": airline_display,
        "money": format_money,
        "day_offset_label": day_offset_label,
        "route_option_summary": route_option_summary,
        "booking_for_instance": booking_for_instance,
        "bookings_for_instance": bookings_for_instance,
        "active_booking_count_for_instance": active_booking_count_for_instance,
        "best_tracker": best_tracker,
        "trip_lifecycle_status_label": trip_lifecycle_status_label,
        "trip_lifecycle_status_tone": trip_lifecycle_status_tone,
        "trip_monitoring_status_label": trip_monitoring_status_label,
        "trip_recommended_action": trip_recommended_action,
        "trip_status_detail": trip_status_detail,
        "rebook_savings": rebook_savings,
        "trip_for_instance": trip_for_instance,
        "group_for_trip": group_for_trip,
        "groups_for_trip": groups_for_trip,
        "group_for_instance": group_for_instance,
        "groups_for_instance": groups_for_instance,
        "groups_for_rule": groups_for_rule,
        "recurring_rule_for_instance": recurring_rule_for_instance,
    }
    context.update(extra)
    return context
