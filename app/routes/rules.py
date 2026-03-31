from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(include_in_schema=False)


@router.get("/rules")
def redirect_rules() -> RedirectResponse:
    return RedirectResponse(url="/trips", status_code=303)
