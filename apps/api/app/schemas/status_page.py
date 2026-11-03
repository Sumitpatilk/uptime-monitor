import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_slug(value: str) -> str:
    value = value.strip().lower()

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise ValueError(
            "Slug must contain only lowercase letters, numbers, and hyphens."
        )

    return value


class StatusPageCreate(BaseModel):
    slug: str = Field(min_length=3, max_length=100)
    visibility: Literal["public", "private"] = "public"
    enabled: bool = False

    @field_validator("slug")
    @classmethod
    def validate_page_slug(cls, value: str) -> str:
        return validate_slug(value)


class StatusPageUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=3, max_length=100)
    visibility: Literal["public", "private"] | None = None
    enabled: bool | None = None

    @field_validator("slug")
    @classmethod
    def validate_page_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_slug(value)


class StatusPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    slug: str
    visibility: str
    enabled: bool


class PublicMonitorStatus(BaseModel):
    name: str
    status: str
    last_checked_at: datetime | None
    latency_ms: int | None


class PublicIncidentStatus(BaseModel):
    started_at: datetime
    resolved_at: datetime | None
    state: str


class PublicStatusPageRead(BaseModel):
    slug: str
    overall_status: str
    monitors: list[PublicMonitorStatus]
    incidents: list[PublicIncidentStatus]
