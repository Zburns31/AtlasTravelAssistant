"""SSE streaming route for chat.

For the first cut we don't stream individual LLM tokens, but we do emit
structured progress events from the graph execution:

* ``thinking`` — sent immediately so the UI can show its typing
  indicator (the React client also shows one optimistically, so this
  is mostly a heartbeat).
* ``plan_ready`` — payload is the high-level task plan produced by the
    decompose phase.
* ``tool_started`` / ``tool_finished`` — coarse tool lifecycle updates
    from the execute loop.
* ``done`` — payload is the full :class:`ChatResponse` JSON.

Real token-level streaming via ``langgraph.astream_events`` is a
follow-up; the event names are stable so the client won't change.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from atlas.api.handlers import stream_chat_events
from atlas.api.schemas import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat/stream")
async def post_chat_stream(request: ChatRequest) -> EventSourceResponse:
    """Stream chat events as Server-Sent Events."""

    async def event_generator():
        try:
            async for event in stream_chat_events(request):
                yield event
        except Exception as exc:
            logger.exception("Streaming chat failed")
            yield {
                "event": "error",
                "data": '{"detail": ' + '"' + str(exc).replace('"', '\\"') + '"}',
            }

    return EventSourceResponse(event_generator())
