"""SSE streaming route for chat.

For the first cut we don't stream individual LLM tokens — we run the
existing :func:`atlas.api.handlers.handle_chat` and emit two events:

* ``thinking`` — sent immediately so the UI can show its typing
  indicator (the React client also shows one optimistically, so this
  is mostly a heartbeat).
* ``done`` — payload is the full :class:`ChatResponse` JSON.

Real token-level streaming via ``langgraph.astream_events`` is a
follow-up; the event names are stable so the client won't change.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from atlas.api.handlers import handle_chat
from atlas.api.schemas import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat/stream")
async def post_chat_stream(request: ChatRequest) -> EventSourceResponse:
    """Stream chat events as Server-Sent Events."""

    async def event_generator():
        yield {"event": "thinking", "data": "{}"}
        try:
            # ``handle_chat`` is sync and may take a while — run in a
            # thread so we don't block the event loop.
            response = await asyncio.to_thread(handle_chat, request)
            yield {
                "event": "done",
                "data": response.model_dump_json(),
            }
        except Exception as exc:
            logger.exception("Streaming chat failed")
            yield {
                "event": "error",
                "data": json.dumps({"detail": str(exc)}),
            }

    return EventSourceResponse(event_generator())
