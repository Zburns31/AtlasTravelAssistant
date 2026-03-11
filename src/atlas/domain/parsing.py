"""Parse LLM structured output into validated Itinerary domain models.

The agent's synthesise phase produces a JSON object matching the
``ItineraryOut`` schema (simple types — no enums, no frozen models).
This module validates that JSON with Pydantic X→ transforms it into the
strict domain models used by the rest of Atlas (renderers, save/export,
UI components).

Typical flow::

    raw_json: str   = llm.invoke(…).content
    data: dict      = extract_itinerary_json(raw_json)
    llm_out         = ItineraryOut.model_validate(data)
    itinerary       = build_itinerary(llm_out, enriched_query=eq)
    markdown        = itinerary_to_markdown(itinerary)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from atlas.domain.models import (
    Accommodation,
    Activity,
    ActivityCategory,
    ActivityNote,
    DaySource,
    Destination,
    Flight,
    Itinerary,
    ItineraryDay,
    NoteAuthor,
    TransitMode,
    TravelSegment,
    TripPace,
    TripPreferences,
)

logger = logging.getLogger(__name__)


# ── LLM-friendly output schemas ─────────────────────────────────────
# These use plain Python types that LLMs produce reliably.  The
# ``build_itinerary()`` function maps them into the strict domain
# models with enums, frozen configs, validators, etc.
# ─────────────────────────────────────────────────────────────────────


class ActivityOut(BaseModel):
    """An activity as the LLM outputs it."""

    title: str
    description: str = ""
    duration_hours: float = 1.0
    category: str = "sightseeing"
    start_time: str | None = None  # "HH:MM" 24-hr
    end_time: str | None = None
    estimated_cost_usd: float | None = None
    location: str | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("notes", mode="before")
    @classmethod
    def _coerce_notes(cls, v: Any) -> list[str]:
        """Accept a single string or other non-list types as a list."""
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, dict):
            return [str(v)]
        if not isinstance(v, list):
            return [str(v)] if v else []
        return [str(item) for item in v if item]


class TravelSegmentOut(BaseModel):
    """A transit segment as the LLM outputs it."""

    mode: str = "walk"
    duration_minutes: int = 10
    description: str = ""
    estimated_cost_usd: float | None = None


class DayOut(BaseModel):
    """A single itinerary day as the LLM outputs it."""

    date: str  # "YYYY-MM-DD"
    activities: list[ActivityOut] = Field(default_factory=list)
    travel_segments: list[TravelSegmentOut] = Field(default_factory=list)
    weather_summary: str = ""


class FlightOut(BaseModel):
    """Flight info as the LLM outputs it."""

    airline: str = ""
    flight_number: str = ""
    departure_airport: str = ""
    arrival_airport: str = ""
    departure_time: str = ""  # "YYYY-MM-DD HH:MM"
    arrival_time: str = ""
    duration_hours: float = 0.0
    cabin_class: str = "economy"
    estimated_cost_usd: float | None = None


class AccommodationOut(BaseModel):
    """Accommodation info as the LLM outputs it."""

    name: str
    star_rating: float | None = None
    nightly_rate_usd: float | None = None
    total_cost_usd: float | None = None
    check_in: str = ""  # "YYYY-MM-DD"
    check_out: str = ""
    description: str = ""
    location: str | None = None


class ItineraryOut(BaseModel):
    """Top-level LLM output schema — simplified for reliable generation.

    Every field uses plain ``str`` / ``float`` / ``list`` types so that
    LLMs can produce valid JSON without needing to know about Python
    enums, frozen Pydantic models, or datetime parsing.

    Validators coerce single-object values into lists so that LLMs
    that emit ``"flights": {...}`` instead of ``"flights": [{...}]``
    are handled gracefully.
    """

    destination_name: str
    destination_country: str
    destination_lat: float | None = None
    destination_lon: float | None = None
    start_date: str  # "YYYY-MM-DD"
    end_date: str  # "YYYY-MM-DD"
    flights: list[FlightOut] = Field(default_factory=list)
    accommodations: list[AccommodationOut] = Field(default_factory=list)
    days: list[DayOut] = Field(default_factory=list)

    @field_validator("flights", mode="before")
    @classmethod
    def _coerce_flights(cls, v: Any) -> list:
        """Wrap a single flight dict into a list."""
        if isinstance(v, dict):
            return [v]
        if not isinstance(v, list):
            return []
        return v

    @field_validator("accommodations", mode="before")
    @classmethod
    def _coerce_accommodations(cls, v: Any) -> list:
        """Wrap a single accommodation dict into a list."""
        if isinstance(v, dict):
            return [v]
        if not isinstance(v, list):
            return []
        return v

    @field_validator("days", mode="before")
    @classmethod
    def _coerce_days(cls, v: Any) -> list:
        """Wrap a single day dict into a list."""
        if isinstance(v, dict):
            return [v]
        if not isinstance(v, list):
            return []
        return v


# ── Safe type converters ─────────────────────────────────────────────


def _safe_category(raw: str) -> ActivityCategory:
    """Parse a category string, falling back to SIGHTSEEING."""
    try:
        return ActivityCategory(raw.lower().strip())
    except ValueError:
        return ActivityCategory.SIGHTSEEING


def _safe_transit_mode(raw: str) -> TransitMode:
    """Parse a transit mode string, falling back to OTHER."""
    try:
        return TransitMode(raw.lower().strip())
    except ValueError:
        return TransitMode.OTHER


def _safe_pace(raw: str) -> TripPace:
    """Parse a pace string, falling back to MODERATE."""
    try:
        return TripPace(raw.lower().strip())
    except ValueError:
        return TripPace.MODERATE


def _parse_date(s: str) -> date:
    """Parse ``YYYY-MM-DD`` string to ``date``."""
    return date.fromisoformat(s.strip())


def _parse_datetime(s: str) -> datetime:
    """Parse a datetime string from common LLM formats.

    Handles ``YYYY-MM-DD HH:MM``, ISO-T format, and with seconds.
    """
    s = s.strip()
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s!r}")


# ── Transform to domain models ──────────────────────────────────────


def build_itinerary(
    output: ItineraryOut,
    *,
    enriched_query: dict | None = None,
) -> Itinerary:
    """Transform an LLM ``ItineraryOut`` into a validated domain ``Itinerary``.

    Parameters
    ----------
    output
        The parsed LLM output (simple types).
    enriched_query
        The enriched query dict from the enrich phase.  Used to fill
        ``TripPreferences`` fields (traveler_count, budget, interests, pace).

    Returns
    -------
    Itinerary
        A fully validated domain model.
    """
    eq = enriched_query or {}

    # Wire destination coordinates when the LLM provides them
    dest_coords: tuple[float, float] | None = None
    if output.destination_lat is not None and output.destination_lon is not None:
        dest_coords = (output.destination_lat, output.destination_lon)

    destination = Destination(
        name=output.destination_name,
        country=output.destination_country,
        coordinates=dest_coords,
    )

    preferences = TripPreferences(
        traveler_count=eq.get("traveler_count", 1) or 1,
        budget_usd=eq.get("budget_usd"),
        interests=eq.get("interests", []),
        pace=_safe_pace(eq.get("pace", "moderate") or "moderate"),
    )

    # ── Transform days ──────────────────────────────────────────────
    days: list[ItineraryDay] = []
    for d in output.days:
        activities: list[Activity] = []
        for a in d.activities:
            notes = [
                ActivityNote(author=NoteAuthor.AGENT, content=n) for n in a.notes if n
            ]
            activities.append(
                Activity(
                    title=a.title,
                    description=a.description,
                    duration_hours=a.duration_hours,
                    category=_safe_category(a.category),
                    start_time=a.start_time,
                    end_time=a.end_time,
                    estimated_cost_usd=a.estimated_cost_usd,
                    location=a.location,
                    notes=notes,
                )
            )

        segments = [
            TravelSegment(
                mode=_safe_transit_mode(s.mode),
                duration_minutes=s.duration_minutes,
                description=s.description,
                estimated_cost_usd=s.estimated_cost_usd,
            )
            for s in d.travel_segments
        ]

        try:
            day_date = _parse_date(d.date)
        except ValueError:
            logger.warning("Skipping day with unparseable date: %r", d.date)
            continue

        days.append(
            ItineraryDay(
                date=day_date,
                activities=activities,
                travel_segments=segments,
                notes=d.weather_summary,
                source=DaySource.GENERATED,
            )
        )

    # ── Transform flights ───────────────────────────────────────────
    flights: list[Flight] = []
    for f in output.flights:
        try:
            flights.append(
                Flight(
                    airline=f.airline,
                    flight_number=f.flight_number,
                    departure_airport=f.departure_airport,
                    arrival_airport=f.arrival_airport,
                    departure_time=_parse_datetime(f.departure_time),
                    arrival_time=_parse_datetime(f.arrival_time),
                    duration_hours=f.duration_hours,
                    cabin_class=f.cabin_class,
                    estimated_cost_usd=f.estimated_cost_usd,
                )
            )
        except (ValueError, KeyError) as exc:
            logger.warning("Skipping unparseable flight: %s", exc)

    # ── Transform accommodations ────────────────────────────────────
    accommodations: list[Accommodation] = []
    for acc in output.accommodations:
        try:
            accommodations.append(
                Accommodation(
                    name=acc.name,
                    star_rating=acc.star_rating,
                    nightly_rate_usd=acc.nightly_rate_usd,
                    total_cost_usd=acc.total_cost_usd,
                    check_in=_parse_date(acc.check_in),
                    check_out=_parse_date(acc.check_out),
                    description=acc.description,
                    location=acc.location,
                )
            )
        except (ValueError, KeyError) as exc:
            logger.warning("Skipping unparseable accommodation: %s", exc)

    return Itinerary(
        destination=destination,
        start_date=_parse_date(output.start_date),
        end_date=_parse_date(output.end_date),
        preferences=preferences,
        days=days,
        flights=flights,
        accommodations=accommodations,
    )


# ── JSON repair helpers ──────────────────────────────────────────────


def _repair_json(text: str) -> str:
    """Apply targeted fixes for common LLM JSON malformations.

    Handles:
    - Trailing commas before ``}`` or ``]``
    - Single-line ``// comments``
    - Unquoted ``NaN`` / ``Infinity`` / ``undefined`` literals
    - Does NOT attempt to fix structural issues like missing brackets
      (those are handled by Pydantic validators on ingestion).
    """
    # Remove single-line // comments (common in LLM output)
    text = re.sub(r"//[^\n]*", "", text)

    # Replace JS-style literals with JSON-safe values
    text = re.sub(r"\bNaN\b", "null", text)
    text = re.sub(r"\bInfinity\b", "null", text)
    text = re.sub(r"\bundefined\b", "null", text)

    # Remove trailing commas: ", }" or ", ]"
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return text


# ── JSON extraction ─────────────────────────────────────────────────


def extract_itinerary_json(text: str) -> dict:
    """Extract a JSON object from LLM text output.

    Handles markdown code fences, leading/trailing prose, nested
    braces, trailing commas, and other common LLM formatting issues.
    Raises ``ValueError`` if no JSON can be found.
    """
    text = text.strip()

    # Strip markdown code fences.
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try the whole thing first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Apply repairs and retry.
    repaired = _repair_json(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Find the outermost JSON object.
    start = text.find("{")
    if start != -1:
        end = text.rfind("}")
        if end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
            # Try with repairs on the substring.
            try:
                return json.loads(_repair_json(candidate))
            except json.JSONDecodeError as exc:
                logger.debug(
                    "JSON repair failed at position %s: %s",
                    getattr(exc, "pos", "?"),
                    exc,
                )

    raise ValueError("Could not extract JSON from LLM output")


# ── High-level convenience ───────────────────────────────────────────


def _normalise_raw_output(raw_output: Any) -> str:
    """Coerce LLM output content to a plain string.

    ``AIMessage.content`` may be a ``str``, a ``list`` of content
    blocks (Anthropic format), or a ``dict``.  This ensures we always
    hand a ``str`` to the JSON extractor.
    """
    if isinstance(raw_output, str):
        return raw_output
    if isinstance(raw_output, list):
        parts: list[str] = []
        for block in raw_output:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text_val = block.get("text", "")
                if text_val:
                    parts.append(str(text_val))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    if isinstance(raw_output, dict):
        return raw_output.get("text", json.dumps(raw_output))
    return str(raw_output)


def parse_agent_result(
    raw_output: str | list | Any,
    enriched_query: dict | None = None,
) -> Itinerary:
    """End-to-end: raw LLM text → validated ``Itinerary`` model.

    Parameters
    ----------
    raw_output
        The raw text content from the synthesise LLM call.  Accepts
        ``str``, ``list`` (Anthropic content blocks), or ``dict``.
    enriched_query
        The enriched query dict for preference filling.

    Returns
    -------
    Itinerary
        Fully validated domain model.

    Raises
    ------
    ValueError
        If the JSON cannot be extracted or validated.
    """
    text = _normalise_raw_output(raw_output)
    data = extract_itinerary_json(text)
    llm_output = ItineraryOut.model_validate(data)
    return build_itinerary(llm_output, enriched_query=enriched_query)
