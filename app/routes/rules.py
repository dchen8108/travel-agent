from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.catalog import FARE_PREFERENCES, TRIP_MODE_OPTIONS, WEEKDAY_OPTIONS, catalogs_json
from app.services.dashboard import load_snapshot
from app.services.programs import ProgramValidationError, build_program, default_program
from app.services.workflows import sync_program
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_class=HTMLResponse)
def rules(request: Request, repository: Repository = Depends(get_repository)) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    selected_program_id = request.query_params.get("program_id", "")
    selected_program = next(
        (program for program in snapshot.programs if program.program_id == selected_program_id),
        snapshot.programs[0] if snapshot.programs else default_program(),
    )
    return get_templates(request).TemplateResponse(
        request=request,
        name="rules.html",
        context=rules_context(
            request,
            snapshot=snapshot,
            programs=snapshot.programs,
            selected_program=selected_program,
        ),
    )


@router.post("")
async def save_rules(request: Request, repository: Repository = Depends(get_repository)) -> RedirectResponse:
    form = await request.form()
    snapshot = load_snapshot(repository)
    incoming_program_id = str(form.get("program_id", "")).strip()
    existing = next(
        (program for program in snapshot.programs if program.program_id == incoming_program_id),
        None,
    )
    try:
        program = build_program(form, existing)
    except ProgramValidationError as exc:
        selected_program = draft_program_state(form, existing)
        return get_templates(request).TemplateResponse(
            request=request,
            name="rules.html",
            context=rules_context(
                request,
                snapshot=snapshot,
                programs=snapshot.programs,
                selected_program=selected_program,
                error_message=str(exc),
            ),
            status_code=422,
        )
    sync_program(repository, program)
    return RedirectResponse(
        url=f"/rules?program_id={program.program_id}&message=Rule+saved",
        status_code=303,
    )


def rules_context(
    request: Request,
    *,
    snapshot,
    programs,
    selected_program,
    error_message: str = "",
) -> dict[str, object]:
    return base_context(
        request,
        page="rules",
        snapshot=snapshot,
        programs=programs,
        selected_program=selected_program,
        program=selected_program,
        weekday_options=WEEKDAY_OPTIONS,
        fare_preferences=FARE_PREFERENCES,
        trip_mode_options=TRIP_MODE_OPTIONS,
        rules_catalogs_json=catalogs_json(),
        error_message=error_message,
    )


def draft_program_state(form: Mapping[str, object], existing) -> dict[str, object]:
    default = default_program()
    trip_mode = str(form.get("trip_mode", default.trip_mode))
    return {
        "program_id": str(form.get("program_id", "")).strip() or (existing.program_id if existing else "draft"),
        "program_name": str(form.get("program_name", "")).strip(),
        "active": _checkbox_state(form, "active", default=True),
        "trip_mode": trip_mode,
        "origin_airports": str(form.get("origin_airports", "")).strip(),
        "destination_airports": str(form.get("destination_airports", "")).strip(),
        "outbound_weekday": str(form.get("outbound_weekday", default.outbound_weekday)),
        "outbound_time_start": str(form.get("outbound_time_start", default.outbound_time_start)),
        "outbound_time_end": str(form.get("outbound_time_end", default.outbound_time_end)),
        "return_weekday": str(form.get("return_weekday", default.return_weekday or "")).strip(),
        "return_time_start": str(form.get("return_time_start", default.return_time_start)),
        "return_time_end": str(form.get("return_time_end", default.return_time_end)),
        "preferred_airlines": str(form.get("preferred_airlines", "")).strip(),
        "allowed_airlines": str(form.get("allowed_airlines", "")).strip(),
        "fare_preference": str(form.get("fare_preference", default.fare_preference)).strip(),
        "nonstop_only": _checkbox_state(form, "nonstop_only", default=default.nonstop_only),
        "lookahead_weeks": str(form.get("lookahead_weeks", default.lookahead_weeks)),
        "rebook_alert_threshold": str(form.get("rebook_alert_threshold", default.rebook_alert_threshold)),
    }


def _checkbox_state(form: Mapping[str, object], name: str, *, default: bool) -> bool:
    if hasattr(form, "getlist"):
        values = [value for value in form.getlist(name) if value != ""]
        if not values:
            return default
        return values[-1] == "true"
    raw = form.get(name)
    if raw is None:
        return default
    return str(raw) == "true"
