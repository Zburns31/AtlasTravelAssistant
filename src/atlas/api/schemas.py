"""Pydantic request / response schemas for the Atlas API layer.

These models define the contract between the UI (Dash callbacks) and
the domain/agent layer.  They are intentionally separate from the
domain models — API schemas can evolve independently of internal
representations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from atlas.domain.models import Itinerary, ItineraryDay

# ── Chat / Conversation ─────────────────────────────────────────────


class ChatRequest(BaseModel):
    """A user message sent to the travel assistant."""

    message: str = Field(..., min_length=1, description="User message text.")
    session_id: str = Field(
        default="default",
        description="Session identifier for multi-turn conversations.",
    )


class TaskPlanItem(BaseModel):
    """One high-level planning step emitted by the decompose phase."""

    step: int
    task: str
    tools: list[str] = Field(default_factory=list)
    notes: str | None = None


class PlanToolUpdate(BaseModel):
    """A tool lifecycle update associated with a planning step."""

    tool: str | None = None
    args: dict[str, object] | None = None
    content_preview: str | None = None
    status: Literal["started", "finished"]


class PlanDraftDay(BaseModel):
    """A draft itinerary day attached to a planning step."""

    step_id: str
    day_index: int
    day: ItineraryDay


class IncrementalPlanStep(BaseModel):
    """A persisted, incrementally updated planning step."""

    id: str
    step: int
    task: str
    kind: Literal["flight", "accommodation", "day", "generic"] = "generic"
    status: Literal["planned", "in_progress", "completed"] = "planned"
    day_index: int | None = None
    preview_lines: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    notes: str | None = None
    findings: list[str] = Field(default_factory=list)
    tool_updates: list[PlanToolUpdate] = Field(default_factory=list)
    draft_days: list[PlanDraftDay] = Field(default_factory=list)


class IncrementalPlan(BaseModel):
    """Session-scoped planning snapshot used by the live UI."""

    session_id: str = "default"
    status: Literal[
        "planning",
        "researching",
        "synthesising",
        "completed",
    ] = "planning"
    steps: list[IncrementalPlanStep] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatResponse(BaseModel):
    """The assistant's reply, plus any structured itinerary produced."""

    reply: str = Field(..., description="Markdown-formatted assistant reply.")
    task_plan: list[TaskPlanItem] | None = Field(
        default=None,
        description="Ordered high-level agent task plan, if one was produced.",
    )
    incremental_plan: IncrementalPlan | None = Field(
        default=None,
        description="Persisted live planning snapshot for the session.",
    )
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


class HistoryMessage(BaseModel):
    """A single chat history entry in API form."""

    role: str
    content: str


class HistoryResponse(BaseModel):
    """The full chat history and latest persisted plan for a session."""

    session_id: str
    messages: list[HistoryMessage]
    incremental_plan: IncrementalPlan | None = None
