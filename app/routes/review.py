from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(include_in_schema=False)


@router.get("/review")
def redirect_review() -> RedirectResponse:
    return RedirectResponse(url="/resolve", status_code=303)
