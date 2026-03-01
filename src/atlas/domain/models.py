"""Pydantic v2 domain models for the Atlas Travel Assistant.

Every structured concept in Atlas — trips, activities, itineraries, user
profiles — is represented here as a frozen or mutable Pydantic model.
Domain functions and tools operate on these types exclusively.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Enums ───────────────────────────────────────────────────────────
class ActivityCategory(str, Enum):
    """Colour-coded activity types rendered on the itinerary timeline."""

    SIGHTSEEING = "sightseeing"
    FOOD = "food"
    CULTURE = "culture"
    ADVENTURE = "adventure"
    LEISURE = "leisure"


class TripPace(str, Enum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    PACKED = "packed"


class TransitMode(str, Enum):
    WALK = "walk"
    BUS = "bus"
    TRAIN = "train"
    TAXI = "taxi"
    OTHER = "other"


class DaySource(str, Enum):
    """How a day was produced."""

    USER = "user"
    GENERATED = "generated"
    REFINED = "refined"


class NoteAuthor(str, Enum):
    AGENT = "agent"
    USER = "user"


# ── Core models ─────────────────────────────────────────────────────
class TripPreferences(BaseModel):
    """User-stated preferences for a trip request."""

    traveler_count: int = 1
    budget_usd: float | None = None
    interests: list[str] = Field(default_factory=list)
    accessibility_needs: list[str] = Field(default_factory=list)
    pace: TripPace = TripPace.MODERATE


class Destination(BaseModel):
    name: str
    country: str
    iata_code: str | None = None
    coordinates: tuple[float, float] | None = None  # (lat, lon)


class ActivityNote(BaseModel):
    """A note on an activity — authored by the agent or the user."""

    model_config = ConfigDict(frozen=True)

    author: NoteAuthor
    content: str
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Activity(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    description: str
    duration_hours: float
    category: ActivityCategory
    start_time: str | None = None  # "HH:MM" 24-hr
    end_time: str | None = None
    estimated_cost_usd: float | None = None
    location: str | None = None
    coordinates: tuple[float, float] | None = None
    notes: list[ActivityNote] = Field(default_factory=list)


class TravelSegment(BaseModel):
    """Transit between two consecutive activities."""

    model_config = ConfigDict(frozen=True)

    mode: TransitMode
    duration_minutes: int
    description: str
    estimated_cost_usd: float | None = None


class ItineraryDay(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    activities: list[Activity] = Field(default_factory=list)
    travel_segments: list[TravelSegment] = Field(default_factory=list)
    notes: str = ""
    source: DaySource = DaySource.GENERATED


class Flight(BaseModel):
    """Suggested flight — informational only, no booking in v1."""

    model_config = ConfigDict(frozen=True)

    airline: str
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    duration_hours: float
    cabin_class: str = "economy"
    estimated_cost_usd: float | None = None


class Accommodation(BaseModel):
    """Suggested lodging — informational only, no booking in v1."""

    model_config = ConfigDict(frozen=True)

    name: str
    star_rating: float | None = None
    nightly_rate_usd: float | None = None
    total_cost_usd: float | None = None
    check_in: date
    check_out: date
    description: str = ""
    location: str | None = None
    coordinates: tuple[float, float] | None = None


class Itinerary(BaseModel):
    destination: Destination
    start_date: date
    end_date: date
    preferences: TripPreferences = Field(default_factory=TripPreferences)
    days: list[ItineraryDay] = Field(default_factory=list)
    flights: list[Flight] = Field(default_factory=list)
    accommodations: list[Accommodation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserProfile(BaseModel):
    """Persistent user profile built from saved trip history.

    Stored at ``~/.atlas/user_profile.json`` and updated on every
    itinerary save.
    """

    favourite_destination_types: list[str] = Field(default_factory=list)
    favourite_categories: list[str] = Field(default_factory=list)
    preferred_pace: TripPace = TripPace.MODERATE
    typical_budget_usd: float | None = None
    past_destinations: list[str] = Field(default_factory=list)
    trip_count: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
