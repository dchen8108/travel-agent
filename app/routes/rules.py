from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.dashboard import load_snapshot
from app.services.programs import build_program, default_program
from app.services.workflows import sync_program
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_class=HTMLResponse)
def rules(request: Request, repository: Repository = Depends(get_repository)) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    program = snapshot.programs[0] if snapshot.programs else default_program()
    return get_templates(request).TemplateResponse(
        request=request,
        name="rules.html",
        context=base_context(request, page="rules", program=program, snapshot=snapshot),
    )


@router.post("")
async def save_rules(request: Request, repository: Repository = Depends(get_repository)) -> RedirectResponse:
    form = await request.form()
    existing_programs = repository.load_programs()
    existing = existing_programs[0] if existing_programs else None
    program = build_program(form, existing)
    sync_program(repository, program)
    return RedirectResponse(url="/?message=Rules+saved", status_code=303)
