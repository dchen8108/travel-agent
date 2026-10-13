from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.v2_workspace import v2_workspace_payload
from app.storage.repository import Repository
from app.web import get_repository

router = APIRouter(prefix="/api/v2", tags=["v2"])


@router.get("/workspace")
def workspace_api(
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    return v2_workspace_payload(
        snapshot,
        today=date.today(),
        repository=repository,
    )
