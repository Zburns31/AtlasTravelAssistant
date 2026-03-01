"""Shared test fixtures for the Atlas test suite.

All LLM interactions are mocked — tests never hit live APIs.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from atlas.domain.models import (
    Activity,
    ActivityCategory,
    Destination,
    Itinerary,
    ItineraryDay,
    TripPreferences,
)


# ── Ensure settings can be loaded in tests ──────────────────────────
@pytest.fixture(autouse=True)
def _inject_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject required env vars so ``atlas.config`` loads cleanly."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")

    # Clear the lru_cache so each test sees fresh settings.
    from atlas.config import get_settings

    get_settings.cache_clear()


# ── Mock LLM ────────────────────────────────────────────────────────
@pytest.fixture
def mock_llm() -> BaseChatModel:
    """Return a ``MagicMock(spec=BaseChatModel)`` that returns a canned
    ``AIMessage`` by default."""
    llm = MagicMock(spec=BaseChatModel)
    llm.invoke.return_value = AIMessage(content="Mock response from Atlas.")
    # Also mock bind_tools to return a copy that behaves the same.
    llm.bind_tools.return_value = llm
    return llm


# ── Sample domain objects ───────────────────────────────────────────
@pytest.fixture
def sample_destination() -> Destination:
    return Destination(
        name="Kyoto",
        country="Japan",
        iata_code="KIX",
        coordinates=(35.0116, 135.7681),
    )


@pytest.fixture
def sample_preferences() -> TripPreferences:
    return TripPreferences(
        traveler_count=2,
        budget_usd=3000.0,
        interests=["temples", "food", "cherry blossom"],
        pace="moderate",
    )


@pytest.fixture
def sample_itinerary(
    sample_destination: Destination,
    sample_preferences: TripPreferences,
) -> Itinerary:
    return Itinerary(
        destination=sample_destination,
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 6),
        preferences=sample_preferences,
        days=[
            ItineraryDay(
                date=date(2025, 4, 1),
                activities=[
                    Activity(
                        title="Fushimi Inari Shrine",
                        description="Walk the thousand torii gates.",
                        duration_hours=2.5,
                        category=ActivityCategory.SIGHTSEEING,
                        start_time="08:00",
                        end_time="10:30",
                        estimated_cost_usd=0,
                        location="Fushimi Ward",
                    )
                ],
            )
        ],
    )
