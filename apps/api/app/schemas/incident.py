from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    monitor_id: UUID
    started_at: datetime
    resolved_at: datetime | None
    state: str
    summary: str | None
