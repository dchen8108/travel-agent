from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["resolve"])


@router.get("/resolve")
def resolve_index(
    request: Request,
) -> RedirectResponse:
    return RedirectResponse(url="/#needs-linking", status_code=303)


@router.post("/resolve/{unmatched_booking_id}/link")
async def resolve_link(
    unmatched_booking_id: str,
    request: Request,
) -> RedirectResponse:
    return RedirectResponse(
        url=f"/bookings/unmatched/{unmatched_booking_id}/link",
        status_code=307,
    )


@router.post("/resolve/{unmatched_booking_id}/create-trip")
async def resolve_create_trip(
    unmatched_booking_id: str,
    request: Request,
) -> RedirectResponse:
    return RedirectResponse(
        url=f"/bookings/unmatched/{unmatched_booking_id}/create-trip",
        status_code=307,
    )
