"""Render the right-hand sidebar: map, destination info, budget, stats.

Uses Plotly ``scattermapbox`` with free ``carto-darkmatter`` tiles (no
Mapbox token needed) for the activity pin map.
"""

from __future__ import annotations

from collections import Counter

import plotly.graph_objects as go
from dash import dcc, html

from atlas.domain.models import (
    ActivityCategory,
    Itinerary,
)


# ── Category → colour for map pins ──────────────────────────────────

_PIN_COLOUR: dict[ActivityCategory, str] = {
    ActivityCategory.FOOD: "#f59e0b",  # orange
    ActivityCategory.CULTURE: "#a78bfa",  # purple
    ActivityCategory.SIGHTSEEING: "#60a5fa",  # blue
    ActivityCategory.ADVENTURE: "#f87171",  # red
    ActivityCategory.LEISURE: "#2dd4bf",  # teal
}

_CAT_LABEL: dict[ActivityCategory, str] = {
    ActivityCategory.FOOD: "Food",
    ActivityCategory.CULTURE: "Culture",
    ActivityCategory.SIGHTSEEING: "Sightseeing",
    ActivityCategory.ADVENTURE: "Adventure",
    ActivityCategory.LEISURE: "Leisure",
}


# ── Public entry point ──────────────────────────────────────────────


def render_sidebar(itinerary: Itinerary) -> list:
    """Build all sidebar sections from an Itinerary."""
    sections: list = []

    # 1. Map
    sections.append(_render_map(itinerary))

    # 2. Destination info
    sections.append(_render_destination_info(itinerary))

    # 3. Budget table
    sections.append(_render_budget_table(itinerary))

    # 4. Trip stats
    sections.append(_render_trip_stats(itinerary))

    return sections


# ── Map ─────────────────────────────────────────────────────────────


def _render_map(itinerary: Itinerary) -> html.Div:
    """Render a Plotly scattermapbox with colour-coded activity pins."""
    lats: list[float] = []
    lons: list[float] = []
    texts: list[str] = []
    colours: list[str] = []

    # Collect activity coordinates
    for day in itinerary.days:
        for act in day.activities:
            if act.coordinates:
                lats.append(act.coordinates[0])
                lons.append(act.coordinates[1])
                texts.append(act.title)
                colours.append(_PIN_COLOUR.get(act.category, "#e8eaed"))

    # Add accommodation pins
    for acc in itinerary.accommodations:
        if acc.coordinates:
            lats.append(acc.coordinates[0])
            lons.append(acc.coordinates[1])
            texts.append(f"🏨 {acc.name}")
            colours.append("#a78bfa")  # purple for hotels

    # Fallback centre: destination coords or first pin
    center_lat, center_lon = 35.0, 135.7  # default (Kyoto-ish)
    if itinerary.destination.coordinates:
        center_lat, center_lon = itinerary.destination.coordinates
    elif lats:
        center_lat = sum(lats) / len(lats)
        center_lon = sum(lons) / len(lons)

    fig = go.Figure()

    if lats:
        fig.add_trace(
            go.Scattermapbox(
                lat=lats,
                lon=lons,
                mode="markers+text",
                marker=dict(size=12, color=colours),
                text=texts,
                textposition="top center",
                textfont=dict(size=9, color="#fff"),
                hoverinfo="text",
            )
        )

    fig.update_layout(
        mapbox=dict(
            style="carto-darkmatter",
            center=dict(lat=center_lat, lon=center_lon),
            zoom=12 if lats else 10,
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#22262e",
        showlegend=False,
        height=260,
    )

    return html.Div(
        dcc.Graph(
            figure=fig,
            config={"displayModeBar": False, "scrollZoom": True},
            style={"height": "100%", "width": "100%"},
        ),
        className="map-wrap",
    )


# ── Destination info ────────────────────────────────────────────────


def _render_destination_info(itinerary: Itinerary) -> html.Div:
    dest = itinerary.destination
    prefs = itinerary.preferences

    # Coordinate string
    coord_str = ""
    if dest.coordinates:
        coord_str = f"📍 {dest.coordinates[0]:.4f}° N, {dest.coordinates[1]:.4f}° E"

    # Tags from interests
    tags = [
        html.Span(f"🏷️ {interest}", className="tag") for interest in prefs.interests[:5]
    ]

    return html.Div(
        [
            html.H4(f"🏯 {dest.name}, {dest.country}"),
            (
                html.P(
                    dest.description,
                    style={
                        "fontSize": "12px",
                        "color": "var(--muted)",
                        "margin": "4px 0 10px",
                    },
                )
                if dest.description
                else None
            ),
            html.Div(coord_str, className="coord") if coord_str else None,
            html.Div(tags, className="tag-row") if tags else None,
        ],
        className="sidebar-section",
    )


# ── Budget table ────────────────────────────────────────────────────


def _render_budget_table(itinerary: Itinerary) -> html.Div:
    flight_cost = sum(
        f.estimated_cost_usd for f in itinerary.flights if f.estimated_cost_usd
    )
    lodging_cost = sum(
        a.total_cost_usd for a in itinerary.accommodations if a.total_cost_usd
    )
    food_cost = 0.0
    activity_cost = 0.0
    transport_cost = 0.0

    for day in itinerary.days:
        for act in day.activities:
            if act.estimated_cost_usd:
                if act.category == ActivityCategory.FOOD:
                    food_cost += act.estimated_cost_usd
                else:
                    activity_cost += act.estimated_cost_usd
        for seg in day.travel_segments:
            if seg.estimated_cost_usd:
                transport_cost += seg.estimated_cost_usd

    total = flight_cost + lodging_cost + food_cost + activity_cost + transport_cost
    n_days = len(itinerary.days) or 1
    per_day = total / n_days

    rows_data = [
        ("✈️ Flights", flight_cost),
        (
            (
                f"🏨 {(itinerary.accommodations[0].check_out - itinerary.accommodations[0].check_in).days} nights lodging"
                if itinerary.accommodations
                else "🏨 Lodging"
            ),
            lodging_cost,
        ),
        ("🍜 Food & dining", food_cost),
        ("🎟️ Activities & entry", activity_cost),
        ("🚃 Transport (local)", transport_cost),
    ]

    rows = []
    for label, amount in rows_data:
        rows.append(
            html.Tr(
                [
                    html.Td(label),
                    html.Td(f"${amount:,.0f}" if amount else "—"),
                ]
            )
        )
    # Total row
    rows.append(
        html.Tr(
            [
                html.Td(html.B("Total estimate")),
                html.Td(html.B(f"${total:,.0f}")),
            ]
        )
    )

    return html.Div(
        [
            html.H4("💰 Trip Budget Summary"),
            html.Table(rows, className="cost-table"),
            html.P(
                f"~${per_day:,.0f}/day · based on estimates, not live pricing",
                style={
                    "marginTop": "8px",
                    "fontSize": "11px",
                    "color": "var(--dim)",
                },
            ),
        ],
        className="sidebar-section",
    )


# ── Trip stats ──────────────────────────────────────────────────────


def _render_trip_stats(itinerary: Itinerary) -> html.Div:
    n_days = len(itinerary.days)
    total_acts = sum(len(d.activities) for d in itinerary.days)
    total_hours = sum(a.duration_hours for d in itinerary.days for a in d.activities)

    # Category breakdown
    cat_counts: Counter[str] = Counter()
    for day in itinerary.days:
        for act in day.activities:
            cat_counts[_CAT_LABEL.get(act.category, act.category.value)] += 1

    top_cats = ", ".join(f"{cat} ({count})" for cat, count in cat_counts.most_common(3))

    date_range = ""
    if itinerary.days:
        start = itinerary.days[0].date.strftime("%b %d")
        end = itinerary.days[-1].date.strftime("%b %d, %Y")
        date_range = f"📅 {n_days} days · {start}–{end}"

    # Walking distance
    from atlas.domain.models import TransitMode

    walk_minutes = sum(
        seg.duration_minutes
        for day in itinerary.days
        for seg in day.travel_segments
        if seg.mode == TransitMode.WALK
    )
    walk_km = round(walk_minutes * 0.08, 1)  # rough 80m/min pace

    stats = [
        date_range,
        f"🎯 {total_acts} activities planned",
        f"🕐 ~{total_hours:.0f} hrs of scheduled time",
    ]
    if walk_km > 0:
        stats.append(f"🚶 ~{walk_km} km walking total")
    if top_cats:
        stats.append(f"🏷️ Top: {top_cats}")

    return html.Div(
        [
            html.H4("📊 Trip Stats"),
            html.Div(
                [html.Div(s) for s in stats if s],
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "4px",
                    "fontSize": "12px",
                    "color": "var(--muted)",
                },
            ),
        ],
        className="sidebar-section",
    )
