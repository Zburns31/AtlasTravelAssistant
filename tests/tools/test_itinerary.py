"""Tests for the itinerary tools (``atlas.tools.itinerary``)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from atlas.domain.models import (
    Accommodation,
    Activity,
    ActivityCategory,
    ActivityNote,
    Destination,
    Flight,
    Itinerary,
    ItineraryDay,
    NoteAuthor,
    TransitMode,
    TravelSegment,
    TripPreferences,
)
from atlas.tools.itinerary import (
    _format_cost,
    _itinerary_slug,
    _slugify,
    export_itinerary_markdown,
    export_markdown_to_disk,
    itinerary_to_markdown,
    save_itinerary,
    save_itinerary_to_disk,
)


# ── Helper fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def rich_itinerary() -> Itinerary:
    """A fully populated itinerary with flights, accommodation, activities,
    travel segments, and notes."""
    return Itinerary(
        destination=Destination(
            name="Kyoto",
            country="Japan",
            iata_code="KIX",
            coordinates=(35.0116, 135.7681),
        ),
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 3),
        preferences=TripPreferences(
            traveler_count=2,
            budget_usd=5000.0,
            interests=["temples", "food"],
            pace="moderate",
        ),
        flights=[
            Flight(
                airline="Japan Airlines",
                flight_number="JL 401",
                departure_airport="SFO",
                arrival_airport="KIX",
                departure_time=datetime(2025, 4, 1, 10, 0, tzinfo=timezone.utc),
                arrival_time=datetime(2025, 4, 2, 14, 0, tzinfo=timezone.utc),
                duration_hours=11.0,
                cabin_class="economy",
                estimated_cost_usd=850.0,
            ),
            Flight(
                airline="Japan Airlines",
                flight_number="JL 402",
                departure_airport="KIX",
                arrival_airport="SFO",
                departure_time=datetime(2025, 4, 3, 18, 0, tzinfo=timezone.utc),
                arrival_time=datetime(2025, 4, 3, 12, 0, tzinfo=timezone.utc),
                duration_hours=10.5,
                cabin_class="economy",
                estimated_cost_usd=800.0,
            ),
        ],
        accommodations=[
            Accommodation(
                name="Hotel Granvia Kyoto",
                star_rating=4.0,
                nightly_rate_usd=150.0,
                total_cost_usd=300.0,
                check_in=date(2025, 4, 1),
                check_out=date(2025, 4, 3),
                description="Near Kyoto Station",
                location="Kyoto Station Area",
            ),
        ],
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
                        estimated_cost_usd=0.0,
                        location="Fushimi Ward",
                        notes=[
                            ActivityNote(
                                author=NoteAuthor.AGENT,
                                content="Go early to avoid crowds.",
                                links=["https://inari.jp"],
                                tags=["tip"],
                            ),
                        ],
                    ),
                    Activity(
                        title="Nishiki Market Lunch",
                        description="Street food and local produce.",
                        duration_hours=1.5,
                        category=ActivityCategory.FOOD,
                        start_time="11:00",
                        end_time="12:30",
                        estimated_cost_usd=25.0,
                        location="Downtown Kyoto",
                    ),
                ],
                travel_segments=[
                    TravelSegment(
                        mode=TransitMode.TRAIN,
                        duration_minutes=20,
                        description="JR Nara Line to Kyoto Station, then Karasuma Line",
                        estimated_cost_usd=3.0,
                    ),
                ],
            ),
            ItineraryDay(
                date=date(2025, 4, 2),
                activities=[
                    Activity(
                        title="Kinkaku-ji (Golden Pavilion)",
                        description="Iconic Zen temple covered in gold leaf.",
                        duration_hours=1.5,
                        category=ActivityCategory.CULTURE,
                        start_time="09:00",
                        end_time="10:30",
                        estimated_cost_usd=5.0,
                        location="Kita Ward",
                    ),
                ],
                notes="Light day — recovery from travel",
            ),
        ],
        created_at=datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


# ── Unit tests: helpers ──────────────────────────────────────────────────────


class TestSlugify:
    def test_simple(self):
        assert _slugify("Kyoto") == "kyoto"

    def test_with_comma_space(self):
        assert _slugify("Kyoto, Japan") == "kyoto-japan"

    def test_special_chars(self):
        assert _slugify("São Paulo!!! Brazil") == "s-o-paulo-brazil"

    def test_leading_trailing_hyphens(self):
        assert _slugify("--hello--") == "hello"


class TestItinerarySlug:
    def test_slug_format(self, sample_itinerary: Itinerary):
        slug = _itinerary_slug(sample_itinerary)
        assert slug == "kyoto-japan_2025-04-01_2025-04-06"


class TestFormatCost:
    def test_none(self):
        assert _format_cost(None) == "N/A"

    def test_zero(self):
        assert _format_cost(0.0) == "$0.00"

    def test_large(self):
        assert _format_cost(1234.50) == "$1,234.50"


# ── Unit tests: Markdown rendering ──────────────────────────────────────────


class TestItineraryToMarkdown:
    def test_header_present(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "# 🗺️ Trip to Kyoto, Japan" in md

    def test_dates_present(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "2025-04-01 → 2025-04-03" in md

    def test_preferences_present(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "Travelers:** 2" in md
        assert "Moderate" in md
        assert "$5,000.00" in md

    def test_interests_present(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "temples, food" in md

    def test_flights_section(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "## ✈️ Flights" in md
        assert "JL 401" in md
        assert "Japan Airlines" in md
        assert "SFO → KIX" in md
        assert "Outbound" in md
        assert "Return" in md

    def test_accommodation_section(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "## 🏨 Accommodation" in md
        assert "Hotel Granvia Kyoto" in md
        assert "$150.00/night" in md
        assert "$300.00 total" in md

    def test_day_sections(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "## 📅 Day 1" in md
        assert "## 📅 Day 2" in md

    def test_activity_details(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "Fushimi Inari Shrine" in md
        assert "08:00–10:30" in md
        assert "sightseeing" in md
        assert "📍 Fushimi Ward" in md

    def test_activity_notes(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "Go early to avoid crowds" in md
        assert "https://inari.jp" in md

    def test_travel_segments(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "Train" in md
        assert "20 min" in md

    def test_budget_summary(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "## 💰 Budget Summary" in md
        assert "Flights" in md
        assert "$1,650.00" in md  # 850 + 800

    def test_footer(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "Generated by Atlas Travel Assistant" in md
        assert "2025-03-15" in md

    def test_minimal_itinerary(self):
        """An itinerary with no flights, accommodation, or days renders cleanly."""
        it = Itinerary(
            destination=Destination(name="Paris", country="France"),
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 5),
        )
        md = itinerary_to_markdown(it)
        assert "# 🗺️ Trip to Paris, France" in md
        assert "## ✈️ Flights" not in md
        assert "## 🏨 Accommodation" not in md
        assert "## 💰 Budget Summary" in md

    def test_day_notes_rendered(self, rich_itinerary: Itinerary):
        md = itinerary_to_markdown(rich_itinerary)
        assert "Light day — recovery from travel" in md


# ── Integration tests: save to disk (JSON only) ─────────────────────────────


class TestSaveItineraryToDisk:
    def test_creates_json(self, rich_itinerary: Itinerary, tmp_path: Path):
        result = save_itinerary_to_disk(rich_itinerary, directory=tmp_path)
        json_path = Path(result["json_path"])
        assert json_path.exists()
        assert json_path.suffix == ".json"

    def test_no_markdown_created(self, rich_itinerary: Itinerary, tmp_path: Path):
        """save_itinerary_to_disk should NOT produce a .md file."""
        save_itinerary_to_disk(rich_itinerary, directory=tmp_path)
        md_files = list(tmp_path.glob("*.md"))
        assert md_files == []

    def test_json_roundtrip(self, rich_itinerary: Itinerary, tmp_path: Path):
        """The saved JSON can be loaded back into a valid Itinerary."""
        result = save_itinerary_to_disk(rich_itinerary, directory=tmp_path)
        json_content = Path(result["json_path"]).read_text(encoding="utf-8")
        loaded = Itinerary.model_validate_json(json_content)
        assert loaded.destination.name == "Kyoto"
        assert len(loaded.days) == 2
        assert len(loaded.flights) == 2

    def test_slug_in_filename(self, rich_itinerary: Itinerary, tmp_path: Path):
        result = save_itinerary_to_disk(rich_itinerary, directory=tmp_path)
        assert "kyoto-japan" in result["slug"]
        assert "2025-04-01" in result["slug"]

    def test_overwrite_existing(self, rich_itinerary: Itinerary, tmp_path: Path):
        """Saving twice to the same directory overwrites cleanly."""
        save_itinerary_to_disk(rich_itinerary, directory=tmp_path)
        result = save_itinerary_to_disk(rich_itinerary, directory=tmp_path)
        assert Path(result["json_path"]).exists()

    def test_creates_directory_if_missing(
        self, rich_itinerary: Itinerary, tmp_path: Path
    ):
        nested_dir = tmp_path / "a" / "b" / "c"
        result = save_itinerary_to_disk(rich_itinerary, directory=nested_dir)
        assert Path(result["json_path"]).exists()

    def test_result_has_no_markdown_key(
        self, rich_itinerary: Itinerary, tmp_path: Path
    ):
        result = save_itinerary_to_disk(rich_itinerary, directory=tmp_path)
        assert "markdown_path" not in result


# ── Integration tests: export Markdown to Downloads ─────────────────────────


class TestExportMarkdownToDisk:
    def test_creates_md(self, rich_itinerary: Itinerary, tmp_path: Path):
        result = export_markdown_to_disk(rich_itinerary, directory=tmp_path)
        md_path = Path(result["markdown_path"])
        assert md_path.exists()
        assert md_path.suffix == ".md"

    def test_no_json_created(self, rich_itinerary: Itinerary, tmp_path: Path):
        """export_markdown_to_disk should NOT produce a .json file."""
        export_markdown_to_disk(rich_itinerary, directory=tmp_path)
        json_files = list(tmp_path.glob("*.json"))
        assert json_files == []

    def test_md_content_valid(self, rich_itinerary: Itinerary, tmp_path: Path):
        result = export_markdown_to_disk(rich_itinerary, directory=tmp_path)
        md_content = Path(result["markdown_path"]).read_text(encoding="utf-8")
        assert "# 🗺️ Trip to Kyoto, Japan" in md_content
        assert "## 💰 Budget Summary" in md_content

    def test_slug_in_result(self, rich_itinerary: Itinerary, tmp_path: Path):
        result = export_markdown_to_disk(rich_itinerary, directory=tmp_path)
        assert "kyoto-japan" in result["slug"]

    def test_creates_directory_if_missing(
        self, rich_itinerary: Itinerary, tmp_path: Path
    ):
        nested_dir = tmp_path / "downloads" / "trips"
        result = export_markdown_to_disk(rich_itinerary, directory=nested_dir)
        assert Path(result["markdown_path"]).exists()


# ── Integration tests: @tool save_itinerary ─────────────────────────────────


class TestSaveItineraryTool:
    def test_valid_json(self, rich_itinerary: Itinerary, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("atlas.tools.itinerary.ITINERARIES_DIR", tmp_path)
        result = save_itinerary.invoke(
            {"itinerary_json": rich_itinerary.model_dump_json()}
        )
        assert result["status"] == "saved"
        assert "json_path" in result
        assert "markdown_path" not in result

    def test_invalid_json(self):
        result = save_itinerary.invoke({"itinerary_json": "not valid json"})
        assert "error" in result
        assert "Invalid itinerary JSON" in result["error"]

    def test_invalid_itinerary_structure(self):
        """Valid JSON but not a valid Itinerary structure."""
        result = save_itinerary.invoke({"itinerary_json": json.dumps({"foo": "bar"})})
        assert "error" in result

    def test_tool_name(self):
        assert save_itinerary.name == "save_itinerary"

    def test_tool_description(self):
        assert "Save a trip itinerary" in save_itinerary.description


# ── Integration tests: @tool export_itinerary_markdown ──────────────────────


class TestExportItineraryMarkdownTool:
    def test_valid_json(self, rich_itinerary: Itinerary, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("atlas.tools.itinerary.DOWNLOADS_DIR", tmp_path)
        result = export_itinerary_markdown.invoke(
            {"itinerary_json": rich_itinerary.model_dump_json()}
        )
        assert result["status"] == "exported"
        assert "markdown_path" in result
        assert Path(result["markdown_path"]).exists()

    def test_exported_content(
        self, rich_itinerary: Itinerary, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setattr("atlas.tools.itinerary.DOWNLOADS_DIR", tmp_path)
        result = export_itinerary_markdown.invoke(
            {"itinerary_json": rich_itinerary.model_dump_json()}
        )
        content = Path(result["markdown_path"]).read_text(encoding="utf-8")
        assert "# 🗺️ Trip to Kyoto, Japan" in content

    def test_invalid_json(self):
        result = export_itinerary_markdown.invoke({"itinerary_json": "not valid json"})
        assert "error" in result
        assert "Invalid itinerary JSON" in result["error"]

    def test_invalid_itinerary_structure(self):
        result = export_itinerary_markdown.invoke(
            {"itinerary_json": json.dumps({"foo": "bar"})}
        )
        assert "error" in result

    def test_tool_name(self):
        assert export_itinerary_markdown.name == "export_itinerary_markdown"

    def test_tool_description(self):
        assert "Export a trip itinerary" in export_itinerary_markdown.description
