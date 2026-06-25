"""Chat routes — synchronous request/response over JSON."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from atlas.api.handlers import get_chat_history, get_current_plan, handle_chat
from atlas.api.schemas import ChatRequest, ChatResponse, HistoryMessage, HistoryResponse

logger = logging.getLogger(__name__)

router = APIRouter()


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
        incremental_plan=get_current_plan(session_id),
    )
