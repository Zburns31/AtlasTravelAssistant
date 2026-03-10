"""Pydantic request / response schemas for the Atlas API layer.

These models define the contract between the UI (Dash callbacks) and
the domain/agent layer.  They are intentionally separate from the
domain models — API schemas can evolve independently of internal
representations.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from atlas.domain.models import Itinerary


# ── Chat / Conversation ─────────────────────────────────────────────


class ChatRequest(BaseModel):
    """A user message sent to the travel assistant."""

    message: str = Field(..., min_length=1, description="User message text.")
    session_id: str = Field(
        default="default",
        description="Session identifier for multi-turn conversations.",
    )


class ChatResponse(BaseModel):
    """The assistant's reply, plus any structured itinerary produced."""

    reply: str = Field(..., description="Markdown-formatted assistant reply.")
    itinerary: Itinerary | None = Field(
        default=None,
        description="Validated structured itinerary, if one was produced.",
    )
    itinerary_md: str | None = Field(
        default=None,
        description="Rendered Markdown itinerary.",
    )
    session_id: str = "default"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Save / Export ────────────────────────────────────────────────────


class SaveResponse(BaseModel):
    """Result of saving an itinerary to disk."""

    json_path: str
    slug: str


class ExportResponse(BaseModel):
    """Result of exporting an itinerary as Markdown."""

    markdown_path: str
    slug: str


# ── Error ────────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    error: str
    detail: str | None = None
