from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import utcnow


class GmailSyncState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_history_id: str = ""
    last_polled_at: datetime = Field(default_factory=utcnow)

