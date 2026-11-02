import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlertChannelCreate(BaseModel):
    type: str = "email"
    destination: str = Field(min_length=5, max_length=254)

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        value = value.strip().lower()

        if value != "email":
            raise ValueError("Only email alert channels are supported.")

        return value

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        value = value.strip().lower()

        email_pattern = r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"

        if not re.fullmatch(email_pattern, value):
            raise ValueError("Please provide a valid email address.")

        return value


class AlertChannelUpdate(BaseModel):
    enabled: bool


class AlertChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    type: str
    destination: str
    enabled: bool
