from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models.base import ReviewStatus
from app.services.dashboard import load_snapshot
from app.services.review import (
    build_review_contexts,
    candidate_trackers_for_review_item,
    ignore_review_item,
    resolve_review_item,
)
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(prefix="/review", tags=["review"])


@router.get("", response_class=HTMLResponse)
def review_page(request: Request, repository: Repository = Depends(get_repository)) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trackers = snapshot.trackers
    suggestions: dict[str, list[object]] = {}
    for item in snapshot.review_items:
        if item.status != ReviewStatus.OPEN:
            continue
        suggestions[item.review_item_id] = candidate_trackers_for_review_item(item, trackers)
    return get_templates(request).TemplateResponse(
        request=request,
        name="review.html",
        context=base_context(
            request,
            page="review",
            snapshot=snapshot,
            review_contexts=build_review_contexts(snapshot.email_events, snapshot.review_items),
            suggestions=suggestions,
        ),
    )


@router.post("/{review_item_id}/match")
async def match_review_item(
    review_item_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    form = await request.form()
    try:
        resolve_review_item(repository, review_item_id, str(form.get("tracker_id", "")))
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Review item or tracker not found") from exc
    return RedirectResponse(url="/review?message=Review+item+resolved", status_code=303)


@router.post("/{review_item_id}/ignore")
def ignore_item(review_item_id: str, repository: Repository = Depends(get_repository)) -> RedirectResponse:
    try:
        ignore_review_item(repository, review_item_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Review item not found") from exc
    return RedirectResponse(url="/review?message=Review+item+ignored", status_code=303)
