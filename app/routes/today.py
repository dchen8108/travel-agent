from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.dashboard import load_snapshot
from app.services.email_import import import_email_payload
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def today(request: Request, repository: Repository = Depends(get_repository)) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    return get_templates(request).TemplateResponse(
        request=request,
        name="today.html",
        context=base_context(
            request,
            page="today",
            snapshot=snapshot,
            total_trips=len(snapshot.trips),
            open_review_count=len([item for item in snapshot.review_items if item.status == "open"]),
        ),
    )


@router.post("/emails/upload")
async def upload_email(
    email_file: UploadFile = File(...),
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    payload = await email_file.read()
    import_email_payload(repository, email_file.filename or "google-flights.eml", payload)
    return RedirectResponse(url="/review?message=Email+imported", status_code=303)
