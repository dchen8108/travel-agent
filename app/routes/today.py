from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.services.dashboard import load_snapshot
from app.services.review import build_review_contexts
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def today(request: Request, repository: Repository = Depends(get_repository)) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    review_contexts = build_review_contexts(snapshot.email_events, snapshot.review_items)
    return get_templates(request).TemplateResponse(
        request=request,
        name="today.html",
        context=base_context(
            request,
            page="today",
            snapshot=snapshot,
            buckets=snapshot.dashboard,
            review_contexts=review_contexts,
        ),
    )
