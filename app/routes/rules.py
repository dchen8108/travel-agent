from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.catalog import WEEKDAY_OPTIONS, catalogs_json
from app.route_details import parse_route_detail_rankings, route_detail_summary, serialize_route_detail_rankings
from app.services.dashboard import load_snapshot
from app.services.programs import (
    ProgramValidationError,
    build_program,
    default_program,
    duplicate_program,
)
from app.services.workflows import delete_program as delete_program_workflow
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
    existing = next((program for program in snapshot.programs if program.program_id == incoming_program_id), None)
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
    return RedirectResponse(url=f"/rules?program_id={program.program_id}&message=Rule+saved", status_code=303)


@router.post("/duplicate")
async def duplicate_rule(request: Request, repository: Repository = Depends(get_repository)) -> RedirectResponse:
    form = await request.form()
    snapshot = load_snapshot(repository)
    incoming_program_id = str(form.get("program_id", "")).strip()
    existing = next((program for program in snapshot.programs if program.program_id == incoming_program_id), None)
    try:
        built = build_program(form, existing)
        program = duplicate_program(built)
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
    return RedirectResponse(url=f"/rules?program_id={program.program_id}&message=Rule+duplicated", status_code=303)


@router.post("/{program_id}/delete")
def delete_rule(program_id: str, repository: Repository = Depends(get_repository)) -> RedirectResponse:
    snapshot = load_snapshot(repository)
    if not any(program.program_id == program_id for program in snapshot.programs):
        raise HTTPException(status_code=404, detail="Rule not found")
    delete_program_workflow(repository, program_id)
    return RedirectResponse(url="/rules?message=Rule+deleted", status_code=303)


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
        rules_catalogs_json=catalogs_json(),
        selected_route_details=parse_route_details_for_template(selected_program),
        program_route_summaries={program.program_id: route_detail_summary(program.route_detail_rankings) for program in programs},
        program_route_counts={program.program_id: len(parse_route_details_for_template(program)) for program in programs},
        error_message=error_message,
    )


def parse_route_details_for_template(program_like) -> list[dict[str, object]]:
    raw = getattr(program_like, "route_detail_rankings", None)
    if raw is None and isinstance(program_like, dict):
        raw = program_like.get("route_detail_rankings", "")
    try:
        details = parse_route_detail_rankings(raw)
    except ValueError:
        details = []
    return [detail.model_dump(mode="json") for detail in details]


def draft_program_state(form: Mapping[str, object], existing) -> dict[str, object]:
    default = default_program()
    return {
        "program_id": str(form.get("program_id", "")).strip() or (existing.program_id if existing else "draft"),
        "program_name": str(form.get("program_name", "")).strip(),
        "active": _checkbox_state(form, "active", default=True),
        "route_detail_rankings": str(form.get("route_detail_rankings", default.route_detail_rankings)).strip()
        or serialize_route_detail_rankings(parse_route_detail_rankings(default.route_detail_rankings)),
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
