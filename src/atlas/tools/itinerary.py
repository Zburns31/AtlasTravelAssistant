"""Itinerary tools — save, load, and export trip itineraries.

**Persistence** (JSON) — ``~/.atlas/itineraries/<slug>.json``
    Internal storage used by the agent to save and (eventually) reload
    itineraries.  Uses atomic write-then-rename for crash safety.

**Export** (Markdown) — ``~/Downloads/<slug>.md``
    Human-readable trip plan the user can open anywhere (GitHub, Obsidian,
    VS Code, etc.).  Includes flights, accommodation, day-by-day activities,
    travel segments, and a budget summary.
"""

from __future__ import annotations

import logging
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

from atlas.domain.models import (
    Accommodation,
    Activity,
    ActivityCategory,
    Flight,
    Itinerary,
    ItineraryDay,
    TransitMode,
    TravelSegment,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

ITINERARIES_DIR = Path.home() / ".atlas" / "itineraries"
DOWNLOADS_DIR = Path.home() / "Downloads"

_CATEGORY_EMOJI: dict[ActivityCategory, str] = {
    ActivityCategory.SIGHTSEEING: "🏛️",
    ActivityCategory.FOOD: "🍽️",
    ActivityCategory.CULTURE: "🎭",
    ActivityCategory.ADVENTURE: "🧗",
    ActivityCategory.LEISURE: "☕",
}

_TRANSIT_EMOJI: dict[TransitMode, str] = {
    TransitMode.WALK: "🚶",
    TransitMode.BUS: "🚌",
    TransitMode.TRAIN: "🚆",
    TransitMode.TAXI: "🚕",
    TransitMode.OTHER: "🚗",
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _slugify(text: str) -> str:
    """Convert *text* to a filesystem-safe slug.

    >>> _slugify("Kyoto, Japan")
    'kyoto-japan'
    """
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _itinerary_slug(itinerary: Itinerary) -> str:
    """Build a filename slug from destination + dates."""
    dest = _slugify(f"{itinerary.destination.name}-{itinerary.destination.country}")
    return f"{dest}_{itinerary.start_date}_{itinerary.end_date}"


def _format_cost(cost: float | None) -> str:
    if cost is None:
        return "N/A"
    return f"${cost:,.2f}"


def _day_label(d: date) -> str:
    """E.g. ``Monday, April 1``."""
    return d.strftime("%A, %B %-d")


# ── Markdown rendering ──────────────────────────────────────────────────────


def _render_flight_section(flights: list[Flight]) -> str:
    """Render the flights section."""
    if not flights:
        return ""

    lines = ["## ✈️ Flights", ""]
    for i, f in enumerate(flights, 1):
        label = "Outbound" if i == 1 else ("Return" if i == 2 else f"Flight {i}")
        lines.append(f"### {label}")
        lines.append(f"- **{f.flight_number}** ({f.airline}) — {f.cabin_class.title()}")
        dep = f.departure_time.strftime("%Y-%m-%d %H:%M")
        arr = f.arrival_time.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"- {f.departure_airport} → {f.arrival_airport}: "
            f"{dep} → {arr} ({f.duration_hours:.1f}h)"
        )
        lines.append(f"- Est. cost: {_format_cost(f.estimated_cost_usd)}")
        lines.append("")

    return "\n".join(lines)


def _render_accommodation_section(accommodations: list[Accommodation]) -> str:
    """Render the accommodation section."""
    if not accommodations:
        return ""

    lines = ["## 🏨 Accommodation", ""]
    for acc in accommodations:
        star_str = ""
        if acc.star_rating is not None:
            full_stars = int(acc.star_rating)
            star_str = f" {'⭐' * full_stars}"
        lines.append(f"### {acc.name}{star_str}")
        lines.append(f"- Check-in: {acc.check_in} → Check-out: {acc.check_out}")
        rate_part = (
            f"{_format_cost(acc.nightly_rate_usd)}/night"
            if acc.nightly_rate_usd
            else ""
        )
        total_part = (
            f" — {_format_cost(acc.total_cost_usd)} total" if acc.total_cost_usd else ""
        )
        if rate_part or total_part:
            lines.append(f"- {rate_part}{total_part}")
        if acc.description:
            lines.append(f"- {acc.description}")
        if acc.location:
            lines.append(f"- 📍 {acc.location}")
        lines.append("")

    return "\n".join(lines)


def _render_activity(activity: Activity) -> list[str]:
    """Render a single activity block."""
    emoji = _CATEGORY_EMOJI.get(activity.category, "📌")
    time_range = ""
    if activity.start_time and activity.end_time:
        time_range = f"{activity.start_time}–{activity.end_time} | "

    lines = [f"### {time_range}{activity.title} {emoji} `{activity.category.value}`"]
    if activity.description:
        lines.append(f"> {activity.description}")
    details: list[str] = []
    if activity.location:
        details.append(f"📍 {activity.location}")
    if activity.estimated_cost_usd is not None:
        details.append(f"💰 {_format_cost(activity.estimated_cost_usd)}")
    details.append(f"⏱️ {activity.duration_hours:.1f}h")
    lines.append(f"- {' · '.join(details)}")

    # Render notes (agent tips, links, user notes)
    for note in activity.notes:
        prefix = "💡" if note.author.value == "agent" else "📝"
        lines.append(f"- {prefix} {note.content}")
        for link in note.links:
            lines.append(f"  - 🔗 {link}")

    return lines


def _render_travel_segment(segment: TravelSegment) -> list[str]:
    """Render a travel segment between activities."""
    emoji = _TRANSIT_EMOJI.get(segment.mode, "🚗")
    cost = (
        f" · {_format_cost(segment.estimated_cost_usd)}"
        if segment.estimated_cost_usd
        else ""
    )
    return [
        "",
        f"> {emoji} **{segment.mode.value.title()}** — "
        f"{segment.duration_minutes} min{cost}",
        f"> {segment.description}" if segment.description else "",
        "",
    ]


def _render_day(day_num: int, day: ItineraryDay) -> str:
    """Render a full day section."""
    # Compute daily cost
    daily_cost = sum(
        a.estimated_cost_usd for a in day.activities if a.estimated_cost_usd
    )
    transport_cost = sum(
        s.estimated_cost_usd for s in day.travel_segments if s.estimated_cost_usd
    )

    lines = [
        f"## 📅 Day {day_num} — {_day_label(day.date)}",
        "",
    ]

    if day.notes:
        lines.append(f"*{day.notes}*")
        lines.append("")

    # Interleave activities and travel segments
    for i, activity in enumerate(day.activities):
        lines.extend(_render_activity(activity))
        lines.append("")

        # Insert travel segment between consecutive activities
        if i < len(day.travel_segments):
            seg_lines = _render_travel_segment(day.travel_segments[i])
            lines.extend(seg_lines)

    # Daily cost summary
    total_daily = daily_cost + transport_cost
    lines.append(f"**Day {day_num} total:** {_format_cost(total_daily)}")
    lines.append(
        f"(Activities: {_format_cost(daily_cost)} + "
        f"Transport: {_format_cost(transport_cost)})"
    )
    lines.append("")

    return "\n".join(lines)


def _render_budget_summary(itinerary: Itinerary) -> str:
    """Render a total trip budget summary."""
    flight_cost = sum(
        f.estimated_cost_usd for f in itinerary.flights if f.estimated_cost_usd
    )
    lodging_cost = sum(
        a.total_cost_usd for a in itinerary.accommodations if a.total_cost_usd
    )
    daily_costs = 0.0
    for day in itinerary.days:
        daily_costs += sum(
            a.estimated_cost_usd for a in day.activities if a.estimated_cost_usd
        )
        daily_costs += sum(
            s.estimated_cost_usd for s in day.travel_segments if s.estimated_cost_usd
        )

    total = flight_cost + lodging_cost + daily_costs

    lines = [
        "## 💰 Budget Summary",
        "",
        "| Category | Estimated Cost |",
        "|----------|---------------|",
        f"| Flights | {_format_cost(flight_cost)} |",
        f"| Accommodation | {_format_cost(lodging_cost)} |",
        f"| Daily Activities & Transport | {_format_cost(daily_costs)} |",
        f"| **Total** | **{_format_cost(total)}** |",
        "",
    ]
    return "\n".join(lines)


def itinerary_to_markdown(itinerary: Itinerary) -> str:
    """Convert an ``Itinerary`` model to a formatted Markdown string.

    This function is the core renderer — the ``save_itinerary`` tool calls it
    internally, but it is also exported for direct use in tests or UI previews.
    """
    dest = itinerary.destination
    prefs = itinerary.preferences

    # Header
    sections: list[str] = [
        f"# 🗺️ Trip to {dest.name}, {dest.country}",
        "",
        f"**Dates:** {itinerary.start_date} → {itinerary.end_date}  ",
        f"**Travelers:** {prefs.traveler_count} | "
        f"**Pace:** {prefs.pace.value.title()}"
        + (
            f" | **Budget:** {_format_cost(prefs.budget_usd)}"
            if prefs.budget_usd
            else ""
        ),
    ]
    if prefs.interests:
        sections.append(f"**Interests:** {', '.join(prefs.interests)}")
    sections.extend(["", "---", ""])

    # Flights
    flight_md = _render_flight_section(itinerary.flights)
    if flight_md:
        sections.append(flight_md)
        sections.extend(["---", ""])

    # Accommodation
    accom_md = _render_accommodation_section(itinerary.accommodations)
    if accom_md:
        sections.append(accom_md)
        sections.extend(["---", ""])

    # Days
    for i, day in enumerate(itinerary.days, 1):
        sections.append(_render_day(i, day))
        sections.extend(["---", ""])

    # Budget summary
    sections.append(_render_budget_summary(itinerary))

    # Footer
    created = itinerary.created_at.strftime("%Y-%m-%d %H:%M UTC")
    sections.extend(
        [
            "---",
            "",
            f"*Generated by Atlas Travel Assistant on {created}*",
            "",
        ]
    )

    return "\n".join(sections)


# ── Disk I/O ─────────────────────────────────────────────────────────────────


def _ensure_dir(path: Path) -> None:
    """Create directory (and parents) if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically (write-then-rename).

    Prevents corruption if the process is interrupted mid-write.
    """
    _ensure_dir(path.parent)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    )
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        Path(tmp.name).replace(path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise


def save_itinerary_to_disk(
    itinerary: Itinerary,
    *,
    directory: Path | None = None,
) -> dict[str, str]:
    """Persist an ``Itinerary`` as a JSON file for internal storage.

    Parameters
    ----------
    itinerary
        The itinerary to save.
    directory
        Override the storage directory (defaults to ``~/.atlas/itineraries``).

    Returns
    -------
    dict
        ``{"json_path": ..., "slug": ...}``
    """
    target_dir = directory or ITINERARIES_DIR
    slug = _itinerary_slug(itinerary)
    json_path = target_dir / f"{slug}.json"

    json_content = itinerary.model_dump_json(indent=2)
    _atomic_write(json_path, json_content)

    logger.info("Saved itinerary to %s", json_path)

    return {
        "json_path": str(json_path),
        "slug": slug,
    }


def export_markdown_to_disk(
    itinerary: Itinerary,
    *,
    directory: Path | None = None,
) -> dict[str, str]:
    """Export an ``Itinerary`` as a Markdown file to the user's Downloads folder.

    Parameters
    ----------
    itinerary
        The itinerary to export.
    directory
        Override the export directory (defaults to ``~/Downloads``).

    Returns
    -------
    dict
        ``{"markdown_path": ..., "slug": ...}``
    """
    target_dir = directory or DOWNLOADS_DIR
    slug = _itinerary_slug(itinerary)
    md_path = target_dir / f"{slug}.md"

    markdown = itinerary_to_markdown(itinerary)
    _atomic_write(md_path, markdown)

    logger.info("Exported itinerary markdown to %s", md_path)

    return {
        "markdown_path": str(md_path),
        "slug": slug,
    }


# ── LangChain tool ──────────────────────────────────────────────────────────


@tool
def save_itinerary(itinerary_json: str) -> dict:
    """Save a trip itinerary to disk as a JSON file.

    Persists the itinerary to ``~/.atlas/itineraries/`` so it can be
    loaded again in a future session.

    Parameters
    ----------
    itinerary_json
        A JSON string representing a valid ``Itinerary`` object.

    Returns
    -------
    dict
        Path to the saved JSON file and the itinerary slug, or an error.
    """
    try:
        itinerary = Itinerary.model_validate_json(itinerary_json)
    except Exception as exc:
        logger.error("Failed to validate itinerary JSON: %s", exc)
        return {"error": f"Invalid itinerary JSON: {exc}"}

    try:
        result = save_itinerary_to_disk(itinerary)
        return {
            "status": "saved",
            "json_path": result["json_path"],
            "slug": result["slug"],
        }
    except Exception as exc:
        logger.error("Failed to save itinerary: %s", exc)
        return {"error": f"Failed to save itinerary: {exc}"}


@tool
def export_itinerary_markdown(itinerary_json: str) -> dict:
    """Export a trip itinerary as a Markdown file to the user's Downloads folder.

    Creates a beautifully formatted ``.md`` file with flights, accommodation,
    day-by-day activities, travel segments, and a budget summary.  The file
    is written to ``~/Downloads/`` so the user can open it in any Markdown
    viewer or share it.

    Parameters
    ----------
    itinerary_json
        A JSON string representing a valid ``Itinerary`` object.

    Returns
    -------
    dict
        Path to the exported Markdown file and the itinerary slug, or an error.
    """
    try:
        itinerary = Itinerary.model_validate_json(itinerary_json)
    except Exception as exc:
        logger.error("Failed to validate itinerary JSON: %s", exc)
        return {"error": f"Invalid itinerary JSON: {exc}"}

    try:
        result = export_markdown_to_disk(itinerary)
        return {
            "status": "exported",
            "markdown_path": result["markdown_path"],
            "slug": result["slug"],
        }
    except Exception as exc:
        logger.error("Failed to export itinerary markdown: %s", exc)
        return {"error": f"Failed to export itinerary markdown: {exc}"}


# TODO: load_itinerary — Load a previously saved itinerary from disk.
# Planned features:
#   - Load from JSON file and reconstruct Itinerary model
#   - List available saved itineraries
#   - Search itineraries by destination or date range
# See: docs/implementation-plan.md Phase 4 — Tool Registry


# ── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    from atlas.domain.models import (
        Accommodation,
        Activity,
        ActivityCategory,
        ActivityNote,
        Destination,
        Flight,
        ItineraryDay,
        NoteAuthor,
        TransitMode,
        TravelSegment,
        TripPreferences,
    )

    sample = Itinerary(
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
            interests=["temples", "food", "cherry blossom"],
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
                description="Connected to Kyoto Station, ideal base for day trips",
                location="Kyoto Station Area",
            ),
        ],
        days=[
            ItineraryDay(
                date=date(2025, 4, 1),
                activities=[
                    Activity(
                        title="Fushimi Inari Shrine",
                        description="Walk the iconic thousand vermillion torii gates.",
                        duration_hours=2.5,
                        category=ActivityCategory.SIGHTSEEING,
                        start_time="08:00",
                        end_time="10:30",
                        estimated_cost_usd=0.0,
                        location="Fushimi Ward",
                        notes=[
                            ActivityNote(
                                author=NoteAuthor.AGENT,
                                content="Go early to avoid crowds. The full hike to the summit takes ~2h.",
                                links=["https://inari.jp/en/"],
                                tags=["tip", "UNESCO"],
                            ),
                        ],
                    ),
                    Activity(
                        title="Nishiki Market Lunch",
                        description="Street food and local produce at 'Kyoto's Kitchen'.",
                        duration_hours=1.5,
                        category=ActivityCategory.FOOD,
                        start_time="11:30",
                        end_time="13:00",
                        estimated_cost_usd=25.0,
                        location="Downtown Kyoto",
                    ),
                    Activity(
                        title="Kinkaku-ji (Golden Pavilion)",
                        description="Iconic Zen temple covered in gold leaf.",
                        duration_hours=1.5,
                        category=ActivityCategory.CULTURE,
                        start_time="14:00",
                        end_time="15:30",
                        estimated_cost_usd=5.0,
                        location="Kita Ward",
                    ),
                ],
                travel_segments=[
                    TravelSegment(
                        mode=TransitMode.TRAIN,
                        duration_minutes=20,
                        description="JR Nara Line to Kyoto Station, then Karasuma Line north",
                        estimated_cost_usd=3.0,
                    ),
                    TravelSegment(
                        mode=TransitMode.BUS,
                        duration_minutes=35,
                        description="City Bus #205 from downtown to Kinkaku-ji",
                        estimated_cost_usd=2.50,
                    ),
                ],
            ),
            ItineraryDay(
                date=date(2025, 4, 2),
                activities=[
                    Activity(
                        title="Arashiyama Bamboo Grove",
                        description="Stroll through towering bamboo stalks.",
                        duration_hours=1.5,
                        category=ActivityCategory.SIGHTSEEING,
                        start_time="09:00",
                        end_time="10:30",
                        estimated_cost_usd=0.0,
                        location="Arashiyama",
                    ),
                    Activity(
                        title="Togetsukyo Bridge & Tea House",
                        description="Relax with matcha overlooking the river.",
                        duration_hours=1.0,
                        category=ActivityCategory.LEISURE,
                        start_time="11:00",
                        end_time="12:00",
                        estimated_cost_usd=8.0,
                        location="Arashiyama",
                    ),
                ],
                travel_segments=[
                    TravelSegment(
                        mode=TransitMode.WALK,
                        duration_minutes=15,
                        description="Scenic walk along the river to Togetsukyo Bridge",
                    ),
                ],
                notes="Light day — enjoy the Arashiyama area at a relaxed pace",
            ),
        ],
    )

    itinerary_json = sample.model_dump_json()

    # --- Save (JSON to ~/.atlas/itineraries/) ---
    print("=" * 60)
    print("SAVE ITINERARY (JSON)")
    print("=" * 60)
    save_result = save_itinerary.invoke({"itinerary_json": itinerary_json})
    print(json.dumps(save_result, indent=2))

    # --- Export (Markdown to ~/Downloads/) ---
    print()
    print("=" * 60)
    print("EXPORT ITINERARY (Markdown)")
    print("=" * 60)
    export_result = export_itinerary_markdown.invoke({"itinerary_json": itinerary_json})
    print(json.dumps(export_result, indent=2))

    # --- Preview the Markdown ---
    if "markdown_path" in export_result:
        print()
        print("=" * 60)
        print("MARKDOWN PREVIEW (first 60 lines)")
        print("=" * 60)
        md = Path(export_result["markdown_path"]).read_text(encoding="utf-8")
        for line in md.splitlines()[:60]:
            print(line)
