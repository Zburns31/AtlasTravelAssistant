"""Tests for domain models (``atlas.domain.models``)."""

from __future__ import annotations

from datetime import date

import pytest

from atlas.domain.models import (
    Activity,
    ActivityCategory,
    ActivityNote,
    Destination,
    Itinerary,
    NoteAuthor,
    TravelSegment,
    TransitMode,
    TripPace,
    TripPreferences,
    UserProfile,
)


def test_itinerary_end_after_start() -> None:
    """``end_date`` must be strictly after ``start_date``."""
    with pytest.raises(ValueError, match="end_date must be after start_date"):
        Itinerary(
            destination=Destination(name="Kyoto", country="Japan"),
            start_date=date(2025, 4, 5),
            end_date=date(2025, 4, 5),
        )


def test_itinerary_valid_dates() -> None:
    it = Itinerary(
        destination=Destination(name="Kyoto", country="Japan"),
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 6),
    )
    assert it.end_date > it.start_date


def test_activity_frozen() -> None:
    """Activities should be immutable (frozen=True)."""
    act = Activity(
        title="Temple visit",
        description="Explore the temple.",
        duration_hours=2.0,
        category=ActivityCategory.CULTURE,
    )
    with pytest.raises(Exception):
        act.title = "Changed"


def test_activity_note_round_trip() -> None:
    note = ActivityNote(
        author=NoteAuthor.AGENT,
        content="Arrive early to avoid crowds.",
        links=["https://example.com"],
        tags=["UNESCO"],
    )
    data = note.model_dump()
    rebuilt = ActivityNote.model_validate(data)
    assert rebuilt.content == note.content
    assert rebuilt.tags == ["UNESCO"]


def test_travel_segment_modes() -> None:
    seg = TravelSegment(
        mode=TransitMode.TRAIN,
        duration_minutes=15,
        description="JR Nara Line → Kyoto Station",
    )
    assert seg.mode == TransitMode.TRAIN


def test_user_profile_defaults() -> None:
    profile = UserProfile()
    assert profile.trip_count == 0
    assert profile.preferred_pace == TripPace.MODERATE
    assert profile.favourite_categories == []


def test_trip_preferences_enum() -> None:
    prefs = TripPreferences(pace="packed")
    assert prefs.pace == TripPace.PACKED


def test_itinerary_serialization(sample_itinerary: Itinerary) -> None:
    """The itinerary should round-trip through JSON."""
    data = sample_itinerary.model_dump(mode="json")
    rebuilt = Itinerary.model_validate(data)
    assert rebuilt.destination.name == "Kyoto"
    assert len(rebuilt.days) == 1
    assert rebuilt.days[0].activities[0].title == "Fushimi Inari Shrine"
