from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.dashboard import load_snapshot
from app.services.email_import import import_email_payload
from app.services.review import build_review_contexts
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("", response_class=HTMLResponse)
def imports_page(request: Request, repository: Repository = Depends(get_repository)) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    review_contexts = build_review_contexts(snapshot.email_events, snapshot.review_items)
    recent_events = sorted(snapshot.email_events, key=lambda item: item.received_at, reverse=True)[:10]
    return get_templates(request).TemplateResponse(
        request=request,
        name="imports.html",
        context=base_context(
            request,
            page="imports",
            snapshot=snapshot,
            recent_events=recent_events,
            review_contexts=review_contexts,
        ),
    )


@router.post("/upload")
async def upload_email(
    email_file: UploadFile = File(...),
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    payload = await email_file.read()
    import_email_payload(repository, email_file.filename or "google-flights.eml", payload)
    return RedirectResponse(url="/imports?message=Email+imported", status_code=303)
