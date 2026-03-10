"""Atlas UI layout — three-panel design matching the mockup.

Panels:
- **Left (340px):** Chat panel — message history + input
- **Center (flex):** Itinerary panel — structured day-by-day view with tabs
- **Right (320px):** Sidebar — map, budget summary, trip info, stats
"""

from __future__ import annotations

from dash import dcc, html


# ── Chat panel (left) ───────────────────────────────────────────────


def _chat_panel() -> html.Div:
    return html.Div(
        [
            # Header
            html.Div(
                [
                    html.Span("💬 Chat"),
                    html.Span(
                        "Session active",
                        style={"fontSize": "10px", "color": "var(--dim)"},
                    ),
                ],
                className="panel-hdr",
            ),
            # Messages
            html.Div(id="chat-display", className="chat-msgs"),
            # Input bar
            html.Div(
                [
                    dcc.Input(
                        id="user-input",
                        placeholder="Describe your trip or refine the itinerary…",
                        type="text",
                        debounce=False,
                        className="chat-in",
                        n_submit=0,
                    ),
                    html.Button("Send", id="send-btn", className="send-btn"),
                ],
                className="chat-bar",
            ),
        ],
        className="chat",
    )


# ── Itinerary panel (center) ────────────────────────────────────────


def _itinerary_panel() -> html.Div:
    return html.Div(
        [
            # Dynamic header — updated by callback
            html.Div(
                [
                    html.H2(
                        "🗺️ Itinerary",
                        id="itinerary-header",
                    ),
                    html.Div(
                        [
                            html.Button("📂 Load", id="load-btn", className="act-btn"),
                            html.Button(
                                "📤 Export", id="export-btn", className="act-btn"
                            ),
                            html.Button(
                                "💾 Save Trip",
                                id="save-btn",
                                className="act-btn primary",
                            ),
                        ],
                        className="acts",
                    ),
                ],
                className="main-hdr",
            ),
            # Tabs
            html.Div(
                [
                    html.Button(
                        "Itinerary",
                        id="tab-itinerary",
                        className="tab active",
                        n_clicks=0,
                    ),
                    html.Button(
                        "Explore",
                        id="tab-explore",
                        className="tab",
                        n_clicks=0,
                    ),
                    html.Button(
                        "Budget",
                        id="tab-budget",
                        className="tab",
                        n_clicks=0,
                    ),
                    html.Button(
                        "Notes",
                        id="tab-notes",
                        className="tab",
                        n_clicks=0,
                    ),
                ],
                className="tabs",
            ),
            # Tab content
            html.Div(
                id="itinerary-display",
                className="main-body",
                children=[
                    html.Div(
                        [
                            html.P("✨ Your itinerary will appear here"),
                            html.P(
                                "Start by typing a trip request in the chat — "
                                'e.g. "Plan a 5-day trip to Kyoto"'
                            ),
                        ],
                        className="empty-state",
                    )
                ],
            ),
        ],
        className="main",
    )


# ── Sidebar panel (right) ───────────────────────────────────────────


def _sidebar_panel() -> html.Div:
    return html.Div(
        [
            # Content area (map + sections, updated by callback)
            html.Div(
                id="sidebar-display",
                children=[
                    html.Div(
                        [
                            html.Div(
                                html.P(
                                    "Trip details and budget summary will appear here.",
                                    style={
                                        "color": "var(--muted)",
                                        "fontSize": "12px",
                                    },
                                ),
                                className="sidebar-section",
                            ),
                        ]
                    )
                ],
                style={"flex": "1", "overflowY": "auto"},
            ),
            # Status bar
            html.Div(
                id="status-bar",
                children="Ready",
                className="status-bar",
            ),
        ],
        className="sidebar",
    )


# ── Navbar ───────────────────────────────────────────────────────────


def _navbar() -> html.Nav:
    return html.Nav(
        [
            html.Div(
                [
                    html.Span(
                        className="globe-icon",
                    ),
                    html.Span("Atlas"),
                ],
                className="nav-brand",
            ),
            html.Div(
                [
                    html.Span(id="model-badge", className="badge-sm"),
                    html.Button(
                        "👤 Profile",
                        id="profile-btn",
                        className="btn-sm",
                        n_clicks=0,
                    ),
                ],
                className="nav-right",
            ),
        ],
        className="atlas-nav",
    )


# ── Profile modal ────────────────────────────────────────────────────


def _profile_modal() -> html.Div:
    """The user-profile modal overlay — hidden by default."""
    return html.Div(
        html.Div(
            [
                # Header
                html.Div(
                    [
                        html.H3("👤 Travel Preferences"),
                        html.Button(
                            "×",
                            id="profile-close-btn",
                            className="modal-close",
                            n_clicks=0,
                        ),
                    ],
                    className="modal-hdr",
                ),
                # Body
                html.Div(
                    [
                        html.Div(
                            [
                                "Trips saved: ",
                                html.Strong(id="profile-trip-count"),
                            ],
                            className="stat",
                        ),
                        html.Div(
                            [
                                "Last updated: ",
                                html.Strong(id="profile-updated-at"),
                            ],
                            className="stat",
                        ),
                        html.Hr(
                            style={
                                "borderColor": "var(--border)",
                                "margin": "12px 0",
                            }
                        ),
                        # Favourite destination types
                        html.Div(
                            [
                                html.Label("Favourite Destination Types"),
                                html.Div(id="profile-dest-types", className="tag-list"),
                                dcc.Input(
                                    id="profile-dest-type-input",
                                    placeholder="Add a type…",
                                    className="chat-in",
                                    style={"marginTop": "6px"},
                                    n_submit=0,
                                ),
                            ],
                            className="fg",
                        ),
                        # Favourite categories
                        html.Div(
                            [
                                html.Label("Favourite Activity Categories"),
                                html.Div(id="profile-categories", className="tag-list"),
                                dcc.Input(
                                    id="profile-category-input",
                                    placeholder="Add a category…",
                                    className="chat-in",
                                    style={"marginTop": "6px"},
                                    n_submit=0,
                                ),
                            ],
                            className="fg",
                        ),
                        # Preferred pace
                        html.Div(
                            [
                                html.Label("Preferred Pace"),
                                dcc.Dropdown(
                                    id="profile-pace",
                                    options=[
                                        {
                                            "label": "Relaxed — 2–3 activities/day",
                                            "value": "relaxed",
                                        },
                                        {
                                            "label": "Moderate — 3–4 activities/day",
                                            "value": "moderate",
                                        },
                                        {
                                            "label": "Packed — 5+ activities/day",
                                            "value": "packed",
                                        },
                                    ],
                                    value="moderate",
                                    clearable=False,
                                    style={
                                        "backgroundColor": "var(--bg4)",
                                        "color": "var(--text)",
                                    },
                                ),
                            ],
                            className="fg",
                        ),
                        # Budget
                        html.Div(
                            [
                                html.Label("Typical Daily Budget (USD)"),
                                dcc.Input(
                                    id="profile-budget",
                                    type="number",
                                    value=150,
                                    className="chat-in",
                                ),
                            ],
                            className="fg",
                        ),
                        # Past destinations (read-only display)
                        html.Div(
                            [
                                html.Label("Past Destinations"),
                                html.Div(id="profile-past-dests", className="tag-list"),
                            ],
                            className="fg",
                        ),
                    ],
                    className="modal-body",
                ),
                # Footer
                html.Div(
                    [
                        html.Button(
                            "Cancel",
                            id="profile-cancel-btn",
                            className="btn-cancel",
                            n_clicks=0,
                        ),
                        html.Button(
                            "Save Profile",
                            id="profile-save-btn",
                            className="btn-save",
                            n_clicks=0,
                        ),
                    ],
                    className="modal-ft",
                ),
            ],
            className="modal-box",
        ),
        id="profile-modal",
        className="modal-overlay",
    )


# ── Full layout ─────────────────────────────────────────────────────


def create_layout() -> html.Div:
    """Build the complete Atlas application layout."""
    return html.Div(
        [
            _navbar(),
            html.Div(
                [
                    _chat_panel(),
                    _itinerary_panel(),
                    _sidebar_panel(),
                ],
                className="app-grid",
            ),
            _profile_modal(),
            # Hidden stores for client-side state.
            dcc.Store(id="chat-history-store", data=[]),
            dcc.Store(id="itinerary-store", data=None),
            dcc.Store(id="session-id-store", data="default"),
            dcc.Store(id="active-tab-store", data="itinerary"),
            dcc.Store(id="pending-msg-store", data=None),
            # Loading overlay for agent calls.
            dcc.Loading(
                id="loading-overlay",
                type="circle",
                children=html.Div(id="loading-trigger"),
                style={
                    "position": "fixed",
                    "top": "50%",
                    "left": "50%",
                    "zIndex": "50",
                },
            ),
        ],
        style={"height": "100vh", "overflow": "hidden"},
    )
