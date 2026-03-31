from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.dashboard import load_snapshot
from app.services.email_import import import_google_flights_email
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["imports"])


@router.get("/imports", response_class=HTMLResponse)
def imports_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    recent_events = sorted(snapshot.email_events, key=lambda item: item.received_at, reverse=True)
    return get_templates(request).TemplateResponse(
        request=request,
        name="imports.html",
        context=base_context(
            request,
            page="imports",
            snapshot=snapshot,
            recent_events=recent_events,
        ),
    )


@router.post("/imports/email")
async def upload_email(
    repository: Repository = Depends(get_repository),
    email_file: UploadFile = File(...),
) -> RedirectResponse:
    payload = await email_file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Email file was empty.")
    import_google_flights_email(
        repository,
        payload=payload,
        filename=email_file.filename or "google-flights.eml",
    )
    sync_and_persist(repository)
    return RedirectResponse(url="/imports?message=Email+imported", status_code=303)
