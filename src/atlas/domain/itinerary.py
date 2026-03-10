"""Itinerary services — render, save, and export trip itineraries.

These are **application-level functions** (not LLM tools).  They are
called by the UI layer or domain orchestration code — e.g. after the
agent finishes synthesising a trip plan, or when the user clicks
"Export" / "Save".

**Persistence** (JSON) — ``~/.atlas/itineraries/<slug>.json``
    Internal storage for saving and reloading itineraries.
    Uses atomic write-then-rename for crash safety.

**Export** (Markdown) — ``~/Downloads/<slug>.md``
    Human-readable trip plan the user can open anywhere (GitHub, Obsidian,
    VS Code, etc.).  Includes flights, accommodation, day-by-day activities,
    travel segments, and a budget summary.
"""

from __future__ import annotations

import logging
import re
import tempfile
from datetime import date
from pathlib import Path

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

    This is the core renderer — used by ``export_markdown_to_disk`` and
    can be called directly for UI previews.
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

    Call this from the UI layer (e.g. a "Save" button callback) or
    automatically at the end of the agent pipeline.

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

    Call this from the UI layer (e.g. an "Export" button callback) or
    automatically when the itinerary is ready for display.

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
