"""Chat routes — synchronous request/response over JSON."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from atlas.api.handlers import get_chat_history, handle_chat
from atlas.api.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class HistoryMessage(BaseModel):
    """A single chat history entry in API form."""

    role: str
    content: str


class HistoryResponse(BaseModel):
    """The full chat history for a session."""

    session_id: str
    messages: list[HistoryMessage]


@router.post("/chat", response_model=ChatResponse)
def post_chat(request: ChatRequest) -> ChatResponse:
    """Process a user message through the agent and return the reply."""
    try:
        return handle_chat(request)
    except Exception as exc:
        logger.exception("Chat handler failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history/{session_id}", response_model=HistoryResponse)
def get_history(session_id: str) -> HistoryResponse:
    """Return the chat history for a session as plain role/content dicts."""
    history = get_chat_history(session_id)
    return HistoryResponse(
        session_id=session_id,
        messages=[HistoryMessage(**m) for m in history],
    )
