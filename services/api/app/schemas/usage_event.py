"""UsageEvent schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EventType


class UsageEventCreate(BaseModel):
    """Schema for creating a usage event."""

    event_type: EventType = Field(alias="eventType")
    tokens_input: int | None = Field(default=None, alias="tokensInput")
    tokens_output: int | None = Field(default=None, alias="tokensOutput")
    cost_cents: int | None = Field(default=None, alias="costCents")
    event_metadata: dict[str, Any] | None = Field(default=None, alias="metadata")

    model_config = ConfigDict(populate_by_name=True)


class UsageEventResponse(BaseModel):
    """Schema for usage event response."""

    id: str
    user_id: str = Field(alias="userId")
    event_type: EventType = Field(alias="eventType")
    tokens_input: int | None = Field(default=None, alias="tokensInput")
    tokens_output: int | None = Field(default=None, alias="tokensOutput")
    cost_cents: int | None = Field(default=None, alias="costCents")
    event_metadata: dict[str, Any] | None = Field(default=None, alias="metadata")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
