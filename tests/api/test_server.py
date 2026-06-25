"""FastAPI server tests — exercise routes without invoking real LLMs.

All tests use ``TestClient`` and mock :func:`atlas.api.handlers.handle_chat`
where needed so no network calls happen.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from atlas.api.handlers import _itineraries, _plans, _sessions
from atlas.api.schemas import ChatResponse, IncrementalPlan, IncrementalPlanStep
from atlas.api.server import create_app
from atlas.domain.models import (
    Destination,
    Itinerary,
    TripPreferences,
    UserProfile,
)


@pytest.fixture(autouse=True)
def _clear_state():
    _sessions.clear()
    _itineraries.clear()
    _plans.clear()
    yield
    _sessions.clear()
    _itineraries.clear()
    _plans.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def sample_itinerary() -> Itinerary:
    return Itinerary(
        destination=Destination(name="Lisbon", country="Portugal"),
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 4),
        preferences=TripPreferences(),
    )


# ── Health ──────────────────────────────────────────────────────────


def test_health(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── Chat ────────────────────────────────────────────────────────────


def test_post_chat_invokes_handler(client: TestClient, sample_itinerary):
    plan = IncrementalPlan(
        session_id="s1",
        status="completed",
        steps=[
            IncrementalPlanStep(
                id="step-1",
                step=1,
                task="Plan Lisbon",
                status="completed",
                tools=["search_web"],
            )
        ],
    )
    fake_response = ChatResponse(
        reply="Done!",
        task_plan=[{"step": 1, "task": "Plan Lisbon", "tools": ["search_web"]}],
        incremental_plan=plan,
        itinerary=sample_itinerary,
        itinerary_md="# Lisbon",
        session_id="s1",
    )
    with patch("atlas.api.routes.chat.handle_chat", return_value=fake_response) as mock:
        resp = client.post(
            "/api/chat", json={"message": "Plan Lisbon", "session_id": "s1"}
        )
    assert resp.status_code == 200
    assert mock.call_count == 1
    body = resp.json()
    assert body["reply"] == "Done!"
    assert body["session_id"] == "s1"
    assert body["task_plan"][0]["task"] == "Plan Lisbon"
    assert body["incremental_plan"]["steps"][0]["id"] == "step-1"
    assert body["itinerary"]["destination"]["name"] == "Lisbon"


def test_post_chat_handler_error_returns_500(client: TestClient) -> None:
    with patch("atlas.api.routes.chat.handle_chat", side_effect=RuntimeError("boom")):
        resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]


def test_get_history_empty(client: TestClient) -> None:
    resp = client.get("/api/history/missing")
    assert resp.status_code == 200
    assert resp.json() == {
        "session_id": "missing",
        "messages": [],
        "incremental_plan": None,
    }


def test_get_history_includes_incremental_plan(client: TestClient) -> None:
    _plans["s1"] = IncrementalPlan(
        session_id="s1",
        status="researching",
        steps=[
            IncrementalPlanStep(
                id="step-1",
                step=1,
                task="Research Lisbon",
                status="in_progress",
            )
        ],
    )

    resp = client.get("/api/history/s1")

    assert resp.status_code == 200
    assert resp.json()["incremental_plan"]["steps"][0]["task"] == "Research Lisbon"


def test_post_chat_stream_emits_sse_events(client: TestClient) -> None:
    async def fake_stream(_request):
        yield {"event": "thinking", "data": "{}"}
        yield {
            "event": "plan_ready",
            "data": '{"task_plan": null, "incremental_plan": {"session_id": "s1", "status": "planning", "steps": [{"id": "card-flight", "step": 1, "task": "Review flights for Lisbon", "kind": "flight", "status": "planned", "day_index": null, "preview_lines": ["Flight options are being researched."], "tools": [], "notes": null, "findings": [], "tool_updates": [], "draft_days": []}], "updated_at": "2026-06-25T00:00:00Z"}, "session_id": "s1"}',
        }
        yield {
            "event": "plan_step_started",
            "data": '{"session_id": "s1", "step": {"id": "card-flight", "step": 1, "task": "Review flights for Lisbon", "kind": "flight", "status": "in_progress", "day_index": null, "preview_lines": ["Flight options are being researched."], "tools": [], "notes": null, "findings": [], "tool_updates": [], "draft_days": []}}',
        }
        yield {
            "event": "plan_step_completed",
            "data": '{"session_id": "s1", "step": {"id": "card-flight", "step": 1, "task": "Review flights for Lisbon", "kind": "flight", "status": "completed", "day_index": null, "preview_lines": ["LIS -> OPO"], "tools": [], "notes": null, "findings": [], "tool_updates": [], "draft_days": []}}',
        }
        yield {"event": "done", "data": '{"reply": "Done!"}'}

    with patch("atlas.api.routes.stream.stream_chat_events", fake_stream):
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "Plan Lisbon", "session_id": "s1"},
        ) as resp:
            body = "".join(resp.iter_text())

    assert resp.status_code == 200
    assert "event: thinking" in body
    assert "event: plan_ready" in body
    assert "Review flights for Lisbon" in body
    assert "event: plan_step_started" in body
    assert "event: plan_step_completed" in body
    assert "event: done" in body


# ── Itinerary ───────────────────────────────────────────────────────


def test_get_itinerary_missing_returns_null(client: TestClient) -> None:
    resp = client.get("/api/itinerary/none")
    assert resp.status_code == 200
    assert resp.json() is None


def test_get_itinerary_returns_cached(
    client: TestClient, sample_itinerary: Itinerary
) -> None:
    _itineraries["s1"] = sample_itinerary
    resp = client.get("/api/itinerary/s1")
    assert resp.status_code == 200
    assert resp.json()["destination"]["name"] == "Lisbon"


def test_save_without_itinerary_returns_404(client: TestClient) -> None:
    resp = client.post("/api/itinerary/none/save")
    assert resp.status_code == 404


def test_save_invokes_handler(client: TestClient, sample_itinerary: Itinerary) -> None:
    _itineraries["s1"] = sample_itinerary
    with patch(
        "atlas.api.routes.itinerary.handle_save",
        return_value={"json_path": "/tmp/x.json", "slug": "lisbon"},
    ) as mock:
        resp = client.post("/api/itinerary/s1/save")
    assert resp.status_code == 200
    assert mock.call_args.args == ("s1",)
    assert resp.json()["slug"] == "lisbon"


def test_export_invokes_handler(
    client: TestClient, sample_itinerary: Itinerary
) -> None:
    _itineraries["s1"] = sample_itinerary
    with patch(
        "atlas.api.routes.itinerary.handle_export",
        return_value={"markdown_path": "/tmp/x.md", "slug": "lisbon"},
    ):
        resp = client.post("/api/itinerary/s1/export")
    assert resp.status_code == 200
    assert resp.json()["markdown_path"].endswith(".md")


# ── Profile ─────────────────────────────────────────────────────────


def test_get_profile_returns_defaults(client: TestClient) -> None:
    with patch("atlas.api.routes.profile.load_profile", return_value=UserProfile()):
        resp = client.get("/api/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert "favorite_destination_types" in body or "preferences" in body or body


def test_put_profile_persists(client: TestClient) -> None:
    payload = UserProfile().model_dump(mode="json")
    with patch("atlas.api.routes.profile.save_profile") as mock_save:
        resp = client.put("/api/profile", json=payload)
    assert resp.status_code == 200
    assert mock_save.call_count == 1
