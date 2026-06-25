"""Tests for API schemas and handlers (``atlas.api``)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from atlas.api.handlers import (
    _itineraries,
    _sessions,
    clear_session,
    get_chat_history,
    get_current_itinerary,
    handle_chat,
    handle_export,
    handle_save,
    stream_chat_events,
)
from atlas.api.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    ExportResponse,
    SaveResponse,
)
from atlas.domain.models import (
    Destination,
    Itinerary,
    TripPreferences,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Ensure clean session state between tests."""
    _sessions.clear()
    _itineraries.clear()
    yield
    _sessions.clear()
    _itineraries.clear()


@pytest.fixture
def sample_itinerary() -> Itinerary:
    return Itinerary(
        destination=Destination(name="Kyoto", country="Japan"),
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 6),
        preferences=TripPreferences(
            traveler_count=2, budget_usd=3000.0, interests=["temples"]
        ),
    )


# ── Schema tests ────────────────────────────────────────────────────


class TestSchemas:
    def test_chat_request_requires_message(self) -> None:
        with pytest.raises(Exception):
            ChatRequest(message="")

    def test_chat_request_valid(self) -> None:
        req = ChatRequest(message="Plan a trip to Paris")
        assert req.message == "Plan a trip to Paris"
        assert req.session_id == "default"

    def test_chat_response_serialization(self) -> None:
        resp = ChatResponse(reply="Here is your trip!", session_id="s1")
        data = resp.model_dump()
        assert data["reply"] == "Here is your trip!"
        assert data["task_plan"] is None
        assert data["itinerary"] is None

    def test_save_response(self) -> None:
        resp = SaveResponse(json_path="/tmp/test.json", slug="kyoto-2025")
        assert resp.slug == "kyoto-2025"

    def test_error_response(self) -> None:
        err = ErrorResponse(error="not_found", detail="No itinerary")
        assert err.error == "not_found"


# ── Handler tests ───────────────────────────────────────────────────


class TestHandleChat:
    @patch("atlas.api.handlers.invoke_agent")
    @patch("atlas.api.handlers.get_llm")
    def test_basic_chat(self, mock_get_llm, mock_invoke) -> None:
        """handle_chat should call invoke_agent and return a ChatResponse."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_invoke.return_value = {
            "response": AIMessage(content="Here is your Kyoto trip!"),
            "task_plan": [
                {
                    "step": 1,
                    "task": "Research Kyoto",
                    "tools": ["search_web"],
                    "notes": "Start broad",
                }
            ],
            "itinerary": None,
            "itinerary_md": None,
        }

        request = ChatRequest(message="Plan a trip to Kyoto")
        response = handle_chat(request)

        assert isinstance(response, ChatResponse)
        assert "Kyoto" in response.reply
        assert response.task_plan is not None
        assert response.task_plan[0]["task"] == "Research Kyoto"
        mock_invoke.assert_called_once()

    @patch("atlas.api.handlers.invoke_agent")
    @patch("atlas.api.handlers.get_llm")
    def test_chat_with_structured_itinerary(
        self, mock_get_llm, mock_invoke, sample_itinerary
    ) -> None:
        """When the agent produces a structured itinerary, it should be included."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_invoke.return_value = {
            "response": AIMessage(content='{"destination_name": "Kyoto"}'),
            "task_plan": [{"step": 1, "task": "Plan Kyoto", "tools": []}],
            "itinerary": sample_itinerary,
            "itinerary_md": "# Trip to Kyoto\n...",
        }

        request = ChatRequest(message="Plan Kyoto trip")
        response = handle_chat(request)

        assert response.itinerary is not None
        assert response.task_plan is not None
        assert response.task_plan[0]["task"] == "Plan Kyoto"
        assert response.itinerary.destination.name == "Kyoto"
        assert response.itinerary_md == "# Trip to Kyoto\n..."
        # Should be cached
        assert get_current_itinerary("default") is sample_itinerary

    @patch("atlas.api.handlers.invoke_agent")
    @patch("atlas.api.handlers.get_llm")
    def test_chat_stores_history(self, mock_get_llm, mock_invoke) -> None:
        """Messages should accumulate in session history."""
        mock_get_llm.return_value = MagicMock()
        mock_invoke.return_value = {
            "response": AIMessage(content="Response 1"),
            "task_plan": None,
            "itinerary": None,
            "itinerary_md": None,
        }

        handle_chat(ChatRequest(message="Hello"))
        handle_chat(ChatRequest(message="Plan a trip"))

        history = get_chat_history("default")
        assert len(history) == 4  # 2 user + 2 assistant


class TestStreamChatEvents:
    @pytest.mark.asyncio
    @patch("atlas.api.handlers.build_travel_agent")
    @patch("atlas.api.handlers.get_llm")
    async def test_stream_emits_plan_and_tool_events(
        self,
        mock_get_llm,
        mock_build_agent,
    ) -> None:
        mock_get_llm.return_value = MagicMock()

        class FakeGraph:
            async def astream(self, *_args, **_kwargs):
                yield {
                    "decompose": {
                        "messages": [],
                        "task_plan": [
                            {
                                "step": 1,
                                "task": "Research Kyoto",
                                "tools": ["search_web"],
                            }
                        ],
                    }
                }
                yield {
                    "execute": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "id": "call_1",
                                        "name": "search_web",
                                        "args": {"query": "Kyoto"},
                                    }
                                ],
                            )
                        ]
                    }
                }
                yield {
                    "tools": {
                        "messages": [
                            SimpleNamespace(
                                content="Top Kyoto attractions...",
                                name="search_web",
                            )
                        ]
                    }
                }
                yield {
                    "synthesise": {
                        "messages": [AIMessage(content="# Kyoto itinerary")],
                        "itinerary": None,
                        "itinerary_md": "# Kyoto itinerary",
                    }
                }

        mock_build_agent.return_value = FakeGraph()

        events = []
        async for event in stream_chat_events(
            ChatRequest(message="Plan Kyoto", session_id="s1")
        ):
            events.append(event)

        assert [event["event"] for event in events] == [
            "thinking",
            "plan_ready",
            "tool_started",
            "tool_finished",
            "done",
        ]
        assert "Research Kyoto" in events[1]["data"]
        assert "search_web" in events[2]["data"]
        assert "Top Kyoto attractions" in events[3]["data"]
        assert "Kyoto itinerary" in events[4]["data"]

        history = get_chat_history("s1")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"


# ── Save/Export handler tests ────────────────────────────────────────


class TestHandleSave:
    def test_save_no_itinerary_raises(self) -> None:
        with pytest.raises(ValueError, match="No itinerary found"):
            handle_save("nonexistent")

    def test_save_with_itinerary(self, sample_itinerary, tmp_path) -> None:
        _itineraries["test"] = sample_itinerary

        with patch(
            "atlas.api.handlers.save_itinerary_to_disk",
            return_value={"json_path": str(tmp_path / "test.json"), "slug": "kyoto"},
        ):
            result = handle_save("test")

        assert isinstance(result, SaveResponse)
        assert result.slug == "kyoto"


class TestHandleExport:
    def test_export_no_itinerary_raises(self) -> None:
        with pytest.raises(ValueError, match="No itinerary found"):
            handle_export("nonexistent")

    def test_export_with_itinerary(self, sample_itinerary, tmp_path) -> None:
        _itineraries["test"] = sample_itinerary

        with patch(
            "atlas.api.handlers.export_markdown_to_disk",
            return_value={
                "markdown_path": str(tmp_path / "test.md"),
                "slug": "kyoto",
            },
        ):
            result = handle_export("test")

        assert isinstance(result, ExportResponse)
        assert result.slug == "kyoto"


# ── Session management ──────────────────────────────────────────────


class TestSessionManagement:
    def test_clear_session(self, sample_itinerary) -> None:
        _sessions["s1"] = []
        _itineraries["s1"] = sample_itinerary

        clear_session("s1")
        assert "s1" not in _sessions
        assert "s1" not in _itineraries

    def test_get_current_itinerary_none(self) -> None:
        assert get_current_itinerary("unknown") is None

    def test_get_chat_history_empty(self) -> None:
        history = get_chat_history("new_session")
        assert history == []
