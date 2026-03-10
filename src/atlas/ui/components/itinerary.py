"""Render a structured Itinerary into Dash HTML components.

Produces flight/accommodation overview cards, day sections with a
timeline, expandable activity cards, and travel connectors — all
matching the ``docs/ui-mockup.html`` design pixel-for-pixel.
"""

from __future__ import annotations

from dash import html

from atlas.domain.models import (
    Accommodation,
    Activity,
    ActivityCategory,
    DaySource,
    Flight,
    Itinerary,
    ItineraryDay,
    NoteAuthor,
    TransitMode,
    TravelSegment,
)


# ── Colour / CSS mappings ───────────────────────────────────────────

_CAT_DOT: dict[ActivityCategory, str] = {
    ActivityCategory.FOOD: "dot-food",
    ActivityCategory.CULTURE: "dot-culture",
    ActivityCategory.SIGHTSEEING: "dot-sightseeing",
    ActivityCategory.ADVENTURE: "dot-adventure",
    ActivityCategory.LEISURE: "dot-leisure",
}

_CAT_BADGE: dict[ActivityCategory, str] = {
    ActivityCategory.FOOD: "cat-food",
    ActivityCategory.CULTURE: "cat-culture",
    ActivityCategory.SIGHTSEEING: "cat-sightseeing",
    ActivityCategory.ADVENTURE: "cat-adventure",
    ActivityCategory.LEISURE: "cat-leisure",
}

_CAT_LABEL: dict[ActivityCategory, str] = {
    ActivityCategory.FOOD: "Food",
    ActivityCategory.CULTURE: "Culture",
    ActivityCategory.SIGHTSEEING: "Sightseeing",
    ActivityCategory.ADVENTURE: "Adventure",
    ActivityCategory.LEISURE: "Leisure",
}

_SOURCE_BADGE: dict[DaySource, tuple[str, str]] = {
    DaySource.USER: ("Your plan", "badge-user"),
    DaySource.GENERATED: ("Generated", "badge-gen"),
    DaySource.REFINED: ("Refined", "badge-refined"),
}

_TRANSIT_ICON: dict[TransitMode, str] = {
    TransitMode.WALK: "🚶",
    TransitMode.BUS: "🚌",
    TransitMode.TRAIN: "🚃",
    TransitMode.TAXI: "🚕",
    TransitMode.OTHER: "🚐",
}


# ── Public entry point ──────────────────────────────────────────────


def render_itinerary(itinerary: Itinerary) -> html.Div:
    """Build the full itinerary panel content from a domain model."""
    children: list = []

    # Flights overview
    if itinerary.flights:
        children.append(_render_flights(itinerary.flights))

    # Accommodation overview
    if itinerary.accommodations:
        children.append(_render_accommodations(itinerary.accommodations))

    # Day-by-day sections
    for idx, day in enumerate(itinerary.days, start=1):
        children.append(_render_day(day, idx))

    return html.Div(children)


def render_itinerary_header(itinerary: Itinerary) -> str:
    """Return the dynamic header text (e.g. '🗾 Kyoto, Japan — 5 Days')."""
    dest = itinerary.destination
    n_days = len(itinerary.days)
    return f"🗾 {dest.name}, {dest.country} — {n_days} Days"


# ── Flights ─────────────────────────────────────────────────────────


def _render_flights(flights: list[Flight]) -> html.Div:
    cards = []
    for f in flights:
        price_str = f"${f.estimated_cost_usd:,.0f}" if f.estimated_cost_usd else "N/A"
        dep_str = f.departure_time.strftime("📅 %b %d, %I:%M %p")
        arr_str = f.arrival_time.strftime("🛬 %b %d, %I:%M %p")
        dur_str = f"{f.duration_hours:.0f}h" if f.duration_hours else ""
        route = f"{f.departure_airport} → {f.arrival_airport}"
        sub = f"{f.airline} {f.flight_number} · {f.cabin_class.title()} · {dur_str} direct"

        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("✈️", className="ov-icon icon-flight"),
                            html.Div(price_str, className="ov-price"),
                        ],
                        className="ov-top",
                    ),
                    html.H4(route),
                    html.Div(sub, className="ov-sub"),
                    html.Div(
                        [html.Span(dep_str), html.Span(arr_str)],
                        className="ov-detail",
                    ),
                ],
                className="ov-card",
            )
        )

    return html.Div(
        [
            html.Div("✈️ Flights", className="section-label"),
            html.Div(cards, className="overview-row"),
        ],
        className="overview-section",
    )


# ── Accommodation ───────────────────────────────────────────────────


def _render_accommodations(accommodations: list[Accommodation]) -> html.Div:
    cards = []
    for a in accommodations:
        price_str = f"${a.total_cost_usd:,.0f}" if a.total_cost_usd else "N/A"
        nights = (a.check_out - a.check_in).days
        star_str = f"{a.star_rating:.0f}-star · " if a.star_rating else ""
        loc_str = f"{a.location} · " if a.location else ""
        sub = (
            f"{star_str}{loc_str}{a.description}"
            if a.description
            else f"{star_str}{loc_str}"
        )
        rate_str = f"${a.nightly_rate_usd:,.0f}/night" if a.nightly_rate_usd else ""
        date_str = f"📅 {a.check_in.strftime('%b %d')} – {a.check_out.strftime('%b %d')} ({nights} nights)"

        detail_items = [html.Span(date_str)]
        if rate_str:
            detail_items.append(html.Span(f"💰 {rate_str}"))

        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("🏨", className="ov-icon icon-hotel"),
                            html.Div(price_str, className="ov-price"),
                        ],
                        className="ov-top",
                    ),
                    html.H4(a.name),
                    html.Div(sub, className="ov-sub"),
                    html.Div(detail_items, className="ov-detail"),
                ],
                className="ov-card",
            )
        )

    return html.Div(
        [
            html.Div("🏨 Accommodation", className="section-label"),
            html.Div(cards, className="overview-row"),
        ],
        className="overview-section",
    )


# ── Day section ─────────────────────────────────────────────────────


def _render_day(day: ItineraryDay, day_num: int) -> html.Div:
    # Source badge
    label_text, badge_cls = _SOURCE_BADGE.get(day.source, ("Generated", "badge-gen"))
    day_label = day.date.strftime("%a, %b %d")

    # Daily cost
    daily_cost = sum(
        a.estimated_cost_usd for a in day.activities if a.estimated_cost_usd
    ) + sum(s.estimated_cost_usd for s in day.travel_segments if s.estimated_cost_usd)
    cost_str = f"~${daily_cost:,.0f}" if daily_cost else ""

    # Weather display (optional)
    weather_span = None
    if day.weather_icon and day.weather_temp_c is not None:
        weather_span = html.Span(
            f"{day.weather_icon} {day.weather_temp_c}°C",
            className="weather",
        )

    meta_children: list = []
    if weather_span:
        meta_children.append(weather_span)
    if cost_str:
        meta_children.append(html.Span(cost_str, className="cost"))

    header = html.Div(
        [
            html.Div(
                [
                    f"Day {day_num} — {day_label} ",
                    html.Span(label_text, className=f"badge {badge_cls}"),
                ],
                className="day-title",
            ),
            html.Div(meta_children, className="day-meta"),
        ],
        className="day-hdr",
    )

    # Refinement banner for refined days
    banner = None
    if day.source == DaySource.REFINED and day.notes:
        banner = html.Div(f"✏️ {day.notes}", className="refine-banner")

    # Timeline: interleave activities and travel segments
    timeline_children: list = []
    segments = list(day.travel_segments)
    for i, activity in enumerate(day.activities):
        # Pass the preceding travel segment for "Getting Here" block
        preceding_segment = (
            segments[i - 1] if i > 0 and (i - 1) < len(segments) else None
        )
        timeline_children.append(
            _render_activity(activity, day_num, i, preceding_segment=preceding_segment)
        )
        # Insert travel segment connector between activities
        if i < len(segments):
            timeline_children.append(_render_travel_segment(segments[i]))

    timeline = html.Div(timeline_children, className="timeline")

    children = [header]
    if banner:
        children.append(banner)
    children.append(timeline)

    return html.Div(children, className="day-section")


# ── Activity card ───────────────────────────────────────────────────


def _render_activity(
    activity: Activity,
    day_num: int,
    act_idx: int,
    *,
    preceding_segment: TravelSegment | None = None,
) -> html.Div:
    dot_cls = _CAT_DOT.get(activity.category, "")
    badge_cls = _CAT_BADGE.get(activity.category, "")
    cat_label = _CAT_LABEL.get(activity.category, activity.category.value.title())
    time_str = activity.start_time or ""
    price_str = (
        f"~${activity.estimated_cost_usd:,.0f}"
        if activity.estimated_cost_usd
        else "Free"
    )

    # Unique ID for expand/collapse
    card_id = f"act-{day_num}-{act_idx}"

    # Detail section (hidden by default, toggled via clientside callback)
    detail = _render_activity_detail(activity, preceding_segment=preceding_segment)

    # Highlighted card border
    card_style = {"borderColor": "var(--orange)"} if activity.highlighted else {}

    return html.Div(
        [
            html.Div(className=f"act-dot {dot_cls}"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(time_str, className="act-time"),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            activity.title,
                                            " ",
                                            html.Span(
                                                cat_label,
                                                className=f"cat {badge_cls}",
                                            ),
                                        ],
                                        className="act-title",
                                    ),
                                ],
                                className="act-info",
                            ),
                            html.Div(price_str, className="act-price"),
                            html.Button(
                                "▾",
                                className="act-toggle",
                                id={"type": "act-toggle", "index": card_id},
                                n_clicks=0,
                            ),
                        ],
                        className="act-top",
                    ),
                    html.Div(
                        detail,
                        className="act-detail",
                        id={"type": "act-detail", "index": card_id},
                    ),
                ],
                className="act-card",
                style=card_style,
            ),
        ],
        className="act-item",
    )


def _render_activity_detail(
    activity: Activity,
    *,
    preceding_segment: TravelSegment | None = None,
) -> list:
    """Build the expandable detail content for an activity card."""
    children: list = []

    # "Getting Here" block (from preceding travel segment)
    if preceding_segment:
        icon = _TRANSIT_ICON.get(preceding_segment.mode, "🚐")
        getting_here_text = (
            f"{preceding_segment.duration_minutes} min · "
            f"{preceding_segment.description}"
        )
        children.append(
            html.Div(
                [html.Span(f"{icon} "), getting_here_text],
                className="detail-getting-here",
            )
        )

    # Description
    if activity.description:
        children.append(html.P(activity.description, className="detail-desc"))

    # Duration meta
    dur_str = f"🕐 {activity.duration_hours:.1f} hrs" if activity.duration_hours else ""
    if dur_str:
        children.append(html.Div([html.Span(dur_str)], className="detail-meta"))

    # Notes (agent and user)
    for note in activity.notes:
        if note.author == NoteAuthor.AGENT:
            children.append(html.Div("🤖 Agent Notes", className="detail-label"))
            children.append(html.Div(note.content, className="detail-note agent-note"))
        elif note.author == NoteAuthor.USER:
            children.append(html.Div("📝 Your Notes", className="detail-label"))
            children.append(html.Div(note.content, className="detail-note user-note"))

        # Links
        if note.links:
            children.append(html.Div("🔗 Links", className="detail-label"))
            children.append(
                html.Div(
                    [
                        html.A(
                            f"🔗 {link}",
                            href=link,
                            target="_blank",
                        )
                        for link in note.links
                    ],
                    className="detail-links",
                )
            )

        # Tags
        if note.tags:
            children.append(
                html.Div(
                    [html.Span(t) for t in note.tags],
                    className="detail-tags",
                )
            )

    return children


# ── Travel connector ────────────────────────────────────────────────


def _render_travel_segment(segment: TravelSegment) -> html.Div:
    icon = _TRANSIT_ICON.get(segment.mode, "🚐")
    dur_str = f"{segment.duration_minutes} min"
    cost_str = (
        f" (~${segment.estimated_cost_usd:,.0f})" if segment.estimated_cost_usd else ""
    )

    return html.Div(
        [
            html.Div(className="conn-dot"),
            html.Div(
                [
                    html.Span(icon, className="conn-icon"),
                    f" {dur_str} · {segment.description}{cost_str}",
                ],
                className="conn-line",
            ),
        ],
        className="travel-conn",
    )
