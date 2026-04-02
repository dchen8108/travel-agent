from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import CsvModel, DataScope, utcnow


class RuleGroupTarget(CsvModel):
    rule_trip_id: str
    trip_group_id: str
    data_scope: DataScope = DataScope.LIVE
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
