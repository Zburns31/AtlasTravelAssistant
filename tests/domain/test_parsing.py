"""Tests for the itinerary parsing module (``atlas.domain.parsing``)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from atlas.domain.models import (
    ActivityCategory,
    DaySource,
    Itinerary,
    NoteAuthor,
    TransitMode,
    TripPace,
)
from atlas.domain.parsing import (
    ActivityOut,
    AccommodationOut,
    DayOut,
    FlightOut,
    ItineraryOut,
    TravelSegmentOut,
    _normalise_raw_output,
    _parse_date,
    _parse_datetime,
    _repair_json,
    _safe_category,
    _safe_pace,
    _safe_transit_mode,
    build_itinerary,
    extract_itinerary_json,
    parse_agent_result,
)


# ── Sample LLM output fixture ──────────────────────────────────────


def _sample_itinerary_out() -> ItineraryOut:
    """Return a minimal but complete ItineraryOut for testing."""
    return ItineraryOut(
        destination_name="Kyoto",
        destination_country="Japan",
        start_date="2025-04-01",
        end_date="2025-04-04",
        flights=[
            FlightOut(
                airline="ANA",
                flight_number="NH123",
                departure_airport="NRT",
                arrival_airport="KIX",
                departure_time="2025-04-01 09:00",
                arrival_time="2025-04-01 10:30",
                duration_hours=1.5,
                cabin_class="economy",
                estimated_cost_usd=250.0,
            ),
        ],
        accommodations=[
            AccommodationOut(
                name="Kyoto Grand Hotel",
                star_rating=4.0,
                nightly_rate_usd=120.0,
                total_cost_usd=360.0,
                check_in="2025-04-01",
                check_out="2025-04-04",
                description="A lovely hotel near Gion district.",
                location="Gion, Kyoto",
            ),
        ],
        days=[
            DayOut(
                date="2025-04-01",
                weather_summary="Sunny, 18°C",
                activities=[
                    ActivityOut(
                        title="Fushimi Inari Shrine",
                        description="Walk the thousand torii gates.",
                        duration_hours=2.5,
                        category="sightseeing",
                        start_time="08:00",
                        end_time="10:30",
                        estimated_cost_usd=0.0,
                        location="Fushimi Ward",
                        notes=["Arrive early to avoid crowds."],
                    ),
                    ActivityOut(
                        title="Nishiki Market Lunch",
                        description="Street food exploration.",
                        duration_hours=1.5,
                        category="food",
                        start_time="11:00",
                        end_time="12:30",
                        estimated_cost_usd=20.0,
                        location="Nishiki Market",
                        notes=[],
                    ),
                ],
                travel_segments=[
                    TravelSegmentOut(
                        mode="train",
                        duration_minutes=25,
                        description="JR Nara Line to Kyoto Station",
                        estimated_cost_usd=3.0,
                    ),
                ],
            ),
        ],
    )


# ── Safe converters ─────────────────────────────────────────────────


class TestSafeConverters:
    def test_safe_category_valid(self) -> None:
        assert _safe_category("food") == ActivityCategory.FOOD
        assert _safe_category("CULTURE") == ActivityCategory.CULTURE
        assert _safe_category(" adventure ") == ActivityCategory.ADVENTURE

    def test_safe_category_invalid_fallback(self) -> None:
        assert _safe_category("unknown_cat") == ActivityCategory.SIGHTSEEING

    def test_safe_transit_mode_valid(self) -> None:
        assert _safe_transit_mode("walk") == TransitMode.WALK
        assert _safe_transit_mode("TRAIN") == TransitMode.TRAIN

    def test_safe_transit_mode_invalid_fallback(self) -> None:
        assert _safe_transit_mode("helicopter") == TransitMode.OTHER

    def test_safe_pace_valid(self) -> None:
        assert _safe_pace("relaxed") == TripPace.RELAXED
        assert _safe_pace("PACKED") == TripPace.PACKED

    def test_safe_pace_invalid_fallback(self) -> None:
        assert _safe_pace("very_fast") == TripPace.MODERATE

    def test_parse_date(self) -> None:
        assert _parse_date("2025-04-01") == date(2025, 4, 1)

    def test_parse_date_with_whitespace(self) -> None:
        assert _parse_date("  2025-04-01 ") == date(2025, 4, 1)

    def test_parse_datetime_space_format(self) -> None:
        dt = _parse_datetime("2025-04-01 09:00")
        assert dt == datetime(2025, 4, 1, 9, 0, tzinfo=timezone.utc)

    def test_parse_datetime_iso_format(self) -> None:
        dt = _parse_datetime("2025-04-01T09:00")
        assert dt == datetime(2025, 4, 1, 9, 0, tzinfo=timezone.utc)

    def test_parse_datetime_with_seconds(self) -> None:
        dt = _parse_datetime("2025-04-01T09:00:30")
        assert dt == datetime(2025, 4, 1, 9, 0, 30, tzinfo=timezone.utc)

    def test_parse_datetime_invalid(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            _parse_datetime("April 1st 2025")


# ── ItineraryOut model ──────────────────────────────────────────────


class TestItineraryOutModel:
    def test_minimal_valid(self) -> None:
        out = ItineraryOut(
            destination_name="Paris",
            destination_country="France",
            start_date="2025-06-01",
            end_date="2025-06-05",
        )
        assert out.destination_name == "Paris"
        assert out.flights == []
        assert out.days == []

    def test_full_round_trip(self) -> None:
        out = _sample_itinerary_out()
        data = out.model_dump()
        rebuilt = ItineraryOut.model_validate(data)
        assert rebuilt.destination_name == "Kyoto"
        assert len(rebuilt.days) == 1
        assert len(rebuilt.days[0].activities) == 2


# ── build_itinerary ─────────────────────────────────────────────────


class TestBuildItinerary:
    def test_basic_transform(self) -> None:
        out = _sample_itinerary_out()
        itinerary = build_itinerary(out)

        assert isinstance(itinerary, Itinerary)
        assert itinerary.destination.name == "Kyoto"
        assert itinerary.destination.country == "Japan"
        assert itinerary.start_date == date(2025, 4, 1)
        assert itinerary.end_date == date(2025, 4, 4)

    def test_days_transformed(self) -> None:
        out = _sample_itinerary_out()
        itinerary = build_itinerary(out)

        assert len(itinerary.days) == 1
        day = itinerary.days[0]
        assert day.date == date(2025, 4, 1)
        assert day.source == DaySource.GENERATED
        assert day.notes == "Sunny, 18°C"

    def test_activities_transformed(self) -> None:
        out = _sample_itinerary_out()
        itinerary = build_itinerary(out)

        activities = itinerary.days[0].activities
        assert len(activities) == 2
        assert activities[0].title == "Fushimi Inari Shrine"
        assert activities[0].category == ActivityCategory.SIGHTSEEING
        assert activities[0].start_time == "08:00"
        assert activities[1].category == ActivityCategory.FOOD

    def test_activity_notes_transformed(self) -> None:
        out = _sample_itinerary_out()
        itinerary = build_itinerary(out)

        notes = itinerary.days[0].activities[0].notes
        assert len(notes) == 1
        assert notes[0].author == NoteAuthor.AGENT
        assert notes[0].content == "Arrive early to avoid crowds."

    def test_travel_segments_transformed(self) -> None:
        out = _sample_itinerary_out()
        itinerary = build_itinerary(out)

        segments = itinerary.days[0].travel_segments
        assert len(segments) == 1
        assert segments[0].mode == TransitMode.TRAIN
        assert segments[0].duration_minutes == 25

    def test_flights_transformed(self) -> None:
        out = _sample_itinerary_out()
        itinerary = build_itinerary(out)

        assert len(itinerary.flights) == 1
        flight = itinerary.flights[0]
        assert flight.airline == "ANA"
        assert flight.departure_airport == "NRT"
        assert flight.duration_hours == 1.5

    def test_accommodations_transformed(self) -> None:
        out = _sample_itinerary_out()
        itinerary = build_itinerary(out)

        assert len(itinerary.accommodations) == 1
        acc = itinerary.accommodations[0]
        assert acc.name == "Kyoto Grand Hotel"
        assert acc.check_in == date(2025, 4, 1)

    def test_enriched_query_fills_preferences(self) -> None:
        out = _sample_itinerary_out()
        enriched = {
            "traveler_count": 2,
            "budget_usd": 3000.0,
            "interests": ["temples", "food"],
            "pace": "packed",
        }
        itinerary = build_itinerary(out, enriched_query=enriched)

        assert itinerary.preferences.traveler_count == 2
        assert itinerary.preferences.budget_usd == 3000.0
        assert itinerary.preferences.interests == ["temples", "food"]
        assert itinerary.preferences.pace == TripPace.PACKED

    def test_default_preferences_without_enriched_query(self) -> None:
        out = _sample_itinerary_out()
        itinerary = build_itinerary(out)

        assert itinerary.preferences.traveler_count == 1
        assert itinerary.preferences.pace == TripPace.MODERATE

    def test_invalid_flight_skipped(self) -> None:
        out = _sample_itinerary_out()
        out.flights.append(
            FlightOut(
                departure_airport="BAD",
                arrival_airport="DATA",
                departure_time="not a datetime",
                arrival_time="also bad",
            )
        )
        itinerary = build_itinerary(out)
        # Only the valid flight survives
        assert len(itinerary.flights) == 1

    def test_invalid_accommodation_skipped(self) -> None:
        out = _sample_itinerary_out()
        out.accommodations.append(
            AccommodationOut(
                name="Bad Hotel",
                check_in="not-a-date",
                check_out="also-bad",
            )
        )
        itinerary = build_itinerary(out)
        assert len(itinerary.accommodations) == 1

    def test_invalid_day_date_skipped(self) -> None:
        out = _sample_itinerary_out()
        out.days.append(DayOut(date="bad-date"))
        itinerary = build_itinerary(out)
        assert len(itinerary.days) == 1

    def test_empty_notes_filtered(self) -> None:
        out = ItineraryOut(
            destination_name="Rome",
            destination_country="Italy",
            start_date="2025-05-01",
            end_date="2025-05-03",
            days=[
                DayOut(
                    date="2025-05-01",
                    activities=[
                        ActivityOut(
                            title="Colosseum",
                            notes=["Good tip", "", "Another tip"],
                        )
                    ],
                )
            ],
        )
        itinerary = build_itinerary(out)
        notes = itinerary.days[0].activities[0].notes
        assert len(notes) == 2  # empty string filtered out


# ── extract_itinerary_json ──────────────────────────────────────────


class TestExtractItineraryJson:
    def test_plain_json(self) -> None:
        data = {"destination_name": "Paris", "destination_country": "France"}
        raw = json.dumps(data)
        assert extract_itinerary_json(raw) == data

    def test_json_in_code_fences(self) -> None:
        raw = '```json\n{"key": "value"}\n```'
        assert extract_itinerary_json(raw) == {"key": "value"}

    def test_json_with_surrounding_text(self) -> None:
        raw = 'Here is the itinerary:\n{"dest": "Rome"}\nEnjoy!'
        assert extract_itinerary_json(raw) == {"dest": "Rome"}

    def test_raises_on_no_json(self) -> None:
        with pytest.raises(ValueError, match="Could not extract JSON"):
            extract_itinerary_json("No JSON here at all.")

    def test_whitespace_handling(self) -> None:
        raw = '  \n  {"a": 1}  \n  '
        assert extract_itinerary_json(raw) == {"a": 1}


# ── parse_agent_result (end-to-end) ─────────────────────────────────


class TestParseAgentResult:
    def test_full_round_trip(self) -> None:
        out = _sample_itinerary_out()
        raw_json = out.model_dump_json()
        itinerary = parse_agent_result(raw_json)

        assert isinstance(itinerary, Itinerary)
        assert itinerary.destination.name == "Kyoto"
        assert len(itinerary.days) == 1
        assert len(itinerary.flights) == 1
        assert len(itinerary.accommodations) == 1

    def test_with_enriched_query(self) -> None:
        out = _sample_itinerary_out()
        raw_json = out.model_dump_json()
        enriched = {"traveler_count": 3, "interests": ["temples"]}
        itinerary = parse_agent_result(raw_json, enriched_query=enriched)

        assert itinerary.preferences.traveler_count == 3
        assert itinerary.preferences.interests == ["temples"]

    def test_json_in_code_fences(self) -> None:
        out = _sample_itinerary_out()
        raw = f"```json\n{out.model_dump_json()}\n```"
        itinerary = parse_agent_result(raw)
        assert itinerary.destination.name == "Kyoto"

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_agent_result("Not valid JSON")

    def test_itinerary_can_render_to_markdown(self) -> None:
        """Integration: parsed itinerary can be fed to the renderer."""
        from atlas.domain.itinerary import itinerary_to_markdown

        out = _sample_itinerary_out()
        raw_json = out.model_dump_json()
        itinerary = parse_agent_result(raw_json)
        md = itinerary_to_markdown(itinerary)

        assert "Kyoto" in md
        assert "Fushimi Inari" in md
        assert "Budget Summary" in md


# ── _repair_json ────────────────────────────────────────────────────


class TestRepairJson:
    def test_trailing_comma_in_object(self) -> None:
        raw = '{"a": 1, "b": 2, }'
        repaired = _repair_json(raw)
        assert json.loads(repaired) == {"a": 1, "b": 2}

    def test_trailing_comma_in_array(self) -> None:
        raw = '["x", "y", ]'
        repaired = _repair_json(raw)
        assert json.loads(repaired) == ["x", "y"]

    def test_nested_trailing_commas(self) -> None:
        raw = '{"items": [1, 2, ], "more": {"nested": 3, }, }'
        repaired = _repair_json(raw)
        assert json.loads(repaired) == {"items": [1, 2], "more": {"nested": 3}}

    def test_single_line_comments_removed(self) -> None:
        raw = '{"key": "val" // a comment\n}'
        repaired = _repair_json(raw)
        assert json.loads(repaired) == {"key": "val"}

    def test_nan_replaced(self) -> None:
        raw = '{"cost": NaN}'
        repaired = _repair_json(raw)
        assert json.loads(repaired) == {"cost": None}

    def test_infinity_replaced(self) -> None:
        raw = '{"val": Infinity}'
        repaired = _repair_json(raw)
        assert json.loads(repaired) == {"val": None}

    def test_undefined_replaced(self) -> None:
        raw = '{"val": undefined}'
        repaired = _repair_json(raw)
        assert json.loads(repaired) == {"val": None}

    def test_clean_json_unchanged(self) -> None:
        raw = '{"a": 1, "b": [2, 3]}'
        assert _repair_json(raw) == raw


# ── _normalise_raw_output ───────────────────────────────────────────


class TestNormaliseRawOutput:
    def test_string_passthrough(self) -> None:
        assert _normalise_raw_output("hello") == "hello"

    def test_list_of_strings(self) -> None:
        result = _normalise_raw_output(["hello", "world"])
        assert result == "hello\nworld"

    def test_anthropic_content_blocks(self) -> None:
        blocks = [
            {"type": "text", "text": '{"destination_name": "Tokyo"}'},
            {"type": "tool_use", "id": "x"},
        ]
        result = _normalise_raw_output(blocks)
        assert '{"destination_name": "Tokyo"}' in result

    def test_dict_with_text_key(self) -> None:
        result = _normalise_raw_output({"text": "some JSON"})
        assert result == "some JSON"

    def test_dict_without_text_key(self) -> None:
        result = _normalise_raw_output({"key": "val"})
        # Should JSON-serialise the dict
        parsed = json.loads(result)
        assert parsed == {"key": "val"}

    def test_other_types_str(self) -> None:
        assert _normalise_raw_output(42) == "42"


# ── Pydantic validators on ItineraryOut ─────────────────────────────


class TestItineraryOutValidators:
    def test_single_flight_dict_wrapped(self) -> None:
        data = {
            "destination_name": "Tokyo",
            "destination_country": "Japan",
            "start_date": "2025-04-01",
            "end_date": "2025-04-05",
            "flights": {
                "airline": "ANA",
                "flight_number": "NH1",
                "departure_airport": "LAX",
                "arrival_airport": "NRT",
                "departure_time": "2025-04-01 10:00",
                "arrival_time": "2025-04-01 14:00",
                "duration_hours": 11.0,
                "cabin_class": "economy",
            },
        }
        out = ItineraryOut.model_validate(data)
        assert len(out.flights) == 1
        assert out.flights[0].airline == "ANA"

    def test_single_accommodation_dict_wrapped(self) -> None:
        data = {
            "destination_name": "Tokyo",
            "destination_country": "Japan",
            "start_date": "2025-04-01",
            "end_date": "2025-04-05",
            "accommodations": {
                "name": "Hotel X",
                "check_in": "2025-04-01",
                "check_out": "2025-04-05",
            },
        }
        out = ItineraryOut.model_validate(data)
        assert len(out.accommodations) == 1
        assert out.accommodations[0].name == "Hotel X"

    def test_single_day_dict_wrapped(self) -> None:
        data = {
            "destination_name": "Tokyo",
            "destination_country": "Japan",
            "start_date": "2025-04-01",
            "end_date": "2025-04-01",
            "days": {"date": "2025-04-01", "activities": []},
        }
        out = ItineraryOut.model_validate(data)
        assert len(out.days) == 1

    def test_flights_list_still_works(self) -> None:
        data = {
            "destination_name": "Tokyo",
            "destination_country": "Japan",
            "start_date": "2025-04-01",
            "end_date": "2025-04-05",
            "flights": [
                {
                    "airline": "ANA",
                    "flight_number": "NH1",
                    "departure_airport": "LAX",
                    "arrival_airport": "NRT",
                    "departure_time": "2025-04-01 10:00",
                    "arrival_time": "2025-04-01 14:00",
                    "duration_hours": 11.0,
                }
            ],
        }
        out = ItineraryOut.model_validate(data)
        assert len(out.flights) == 1

    def test_non_list_flights_returns_empty(self) -> None:
        data = {
            "destination_name": "Tokyo",
            "destination_country": "Japan",
            "start_date": "2025-04-01",
            "end_date": "2025-04-05",
            "flights": "invalid",
        }
        out = ItineraryOut.model_validate(data)
        assert out.flights == []


# ── ActivityOut.notes validator ──────────────────────────────────────


class TestActivityOutNotesValidator:
    def test_string_note_wrapped(self) -> None:
        act = ActivityOut(title="Test", notes="single tip")
        assert act.notes == ["single tip"]

    def test_empty_string_note(self) -> None:
        act = ActivityOut(title="Test", notes="")
        assert act.notes == []

    def test_list_of_strings_kept(self) -> None:
        act = ActivityOut(title="Test", notes=["a", "b"])
        assert act.notes == ["a", "b"]

    def test_empty_items_filtered(self) -> None:
        act = ActivityOut(title="Test", notes=["a", "", "b"])
        assert act.notes == ["a", "b"]

    def test_dict_note_coerced(self) -> None:
        act = ActivityOut(title="Test", notes={"key": "val"})
        assert len(act.notes) == 1
        assert "key" in act.notes[0]


# ── extract_itinerary_json with repairs ─────────────────────────────


class TestExtractWithRepairs:
    def test_json_with_trailing_commas(self) -> None:
        raw = '{"destination_name": "Paris", "country": "France", }'
        result = extract_itinerary_json(raw)
        assert result["destination_name"] == "Paris"

    def test_json_with_comments(self) -> None:
        raw = '{"key": "val" // this is a comment\n}'
        result = extract_itinerary_json(raw)
        assert result["key"] == "val"

    def test_json_wrapped_in_prose_with_trailing_comma(self) -> None:
        raw = 'Here is the result:\n{"a": 1, "b": 2, }\nDone!'
        result = extract_itinerary_json(raw)
        assert result == {"a": 1, "b": 2}


# ── parse_agent_result with flexible inputs ─────────────────────────


class TestParseAgentResultFlexible:
    def test_accepts_list_content_blocks(self) -> None:
        """Anthropic-style list[dict] content should parse fine."""
        out = _sample_itinerary_out()
        blocks = [{"type": "text", "text": out.model_dump_json()}]
        itinerary = parse_agent_result(blocks)
        assert itinerary.destination.name == "Kyoto"

    def test_accepts_plain_string(self) -> None:
        out = _sample_itinerary_out()
        itinerary = parse_agent_result(out.model_dump_json())
        assert itinerary.destination.name == "Kyoto"

    def test_single_object_flights_parsed(self) -> None:
        """LLM returns flights as a single object instead of a list."""
        raw = json.dumps(
            {
                "destination_name": "Rome",
                "destination_country": "Italy",
                "start_date": "2025-06-01",
                "end_date": "2025-06-03",
                "flights": {
                    "airline": "Alitalia",
                    "flight_number": "AZ1",
                    "departure_airport": "JFK",
                    "arrival_airport": "FCO",
                    "departure_time": "2025-06-01 22:00",
                    "arrival_time": "2025-06-02 10:00",
                    "duration_hours": 9.0,
                    "cabin_class": "economy",
                    "estimated_cost_usd": 600.0,
                },
                "accommodations": {
                    "name": "Hotel Roma",
                    "check_in": "2025-06-01",
                    "check_out": "2025-06-03",
                },
                "days": [
                    {
                        "date": "2025-06-01",
                        "activities": [
                            {
                                "title": "Arrive",
                                "start_time": "10:00",
                                "end_time": "12:00",
                            }
                        ],
                    }
                ],
            }
        )
        itinerary = parse_agent_result(raw)
        assert len(itinerary.flights) == 1
        assert itinerary.flights[0].airline == "Alitalia"
        assert len(itinerary.accommodations) == 1
        assert itinerary.accommodations[0].name == "Hotel Roma"

    def test_trailing_comma_json_parsed(self) -> None:
        """LLM produces JSON with trailing commas."""
        raw = """{
            "destination_name": "Berlin",
            "destination_country": "Germany",
            "start_date": "2025-07-01",
            "end_date": "2025-07-03",
            "days": [
                {
                    "date": "2025-07-01",
                    "activities": [
                        {
                            "title": "Brandenburg Gate",
                            "start_time": "09:00",
                            "end_time": "11:00",
                        },
                    ],
                },
            ],
        }"""
        itinerary = parse_agent_result(raw)
        assert itinerary.destination.name == "Berlin"
        assert len(itinerary.days) == 1
