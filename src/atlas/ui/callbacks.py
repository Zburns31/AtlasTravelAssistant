"""Dash callbacks — wire the UI to the API handlers.

All callbacks follow the separation-of-concerns principle:
  Dash callback → API handler → agent/domain
No LLM calls happen directly in callbacks.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any

import dash
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from atlas.api.handlers import (
    get_chat_history,
    handle_chat,
    handle_export,
    handle_save,
)
from atlas.api.schemas import ChatRequest
from atlas.config import get_settings

from atlas.domain.parsing import parse_agent_result
from atlas.ui.components.itinerary import render_itinerary, render_itinerary_header
from atlas.ui.components.profile import load_profile, save_profile
from atlas.ui.components.sidebar import render_sidebar

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────


def _normalise_content(content: Any) -> str:
    """Extract plain-text from LangChain message content.

    ``AIMessage.content`` may be a ``str``, a ``list`` of content blocks
    (e.g. ``[{"type": "text", "text": "..."}]``), or even a dict.  This
    helper always returns a plain string suitable for rendering.

    When the content appears to be a raw JSON itinerary dict, it is
    replaced with a short placeholder — the structured renderer handles
    the real display.
    """
    if isinstance(content, str):
        # Detect raw JSON blobs (e.g. synthesise output dumped as string)
        stripped = content.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = __import__("json").loads(stripped)
                # If it looks like an itinerary JSON, don't dump it in chat
                if isinstance(data, dict) and any(
                    k in data
                    for k in ("destination_name", "days", "itinerary", "destination")
                ):
                    return (
                        "✅ *Itinerary generated!* "
                        "See the itinerary panel for the full plan."
                    )
            except (ValueError, TypeError):
                pass
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # Standard content-block format: {"type": "text", "text": "..."}
                text_val = block.get("text", "")
                if text_val:
                    parts.append(text_val)
                elif block.get("type") == "tool_use":
                    # Skip tool-use blocks — they're not user-facing
                    continue
                else:
                    parts.append(str(block))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    if isinstance(content, dict):
        # If it looks like an itinerary dict, show friendly message
        if any(
            k in content
            for k in ("destination_name", "days", "itinerary", "destination")
        ):
            return (
                "✅ *Itinerary generated!* See the itinerary panel for the full plan."
            )
        return content.get("text", content.get("content", str(content)))
    return str(content)


def _render_message(role: str, content: Any, timestamp: str = "") -> html.Div:
    """Render a single chat message bubble matching the mockup.

    Assistant messages use ``dcc.Markdown`` so formatting (bold, lists,
    links) renders correctly.  User messages stay as plain text.
    """
    is_user = role == "user"
    cls = "msg u" if is_user else "msg a"
    ts_prefix = "" if is_user else "Atlas · "
    if not timestamp:
        timestamp = datetime.now(timezone.utc).strftime("%I:%M %p")

    text = _normalise_content(content)

    # Use Markdown rendering for assistant messages so formatting works.
    if is_user:
        body: Any = text
    else:
        body = dcc.Markdown(
            text,
            style={
                "color": "var(--text)",
                "lineHeight": "1.5",
                "margin": "0",
                "fontSize": "13px",
            },
            className="msg-markdown",
        )

    return html.Div(
        [
            body,
            html.Div(f"{ts_prefix}{timestamp}", className="ts"),
        ],
        className=cls,
    )


def _typing_indicator() -> html.Div:
    """Render an 'Atlas is typing...' indicator."""
    return html.Div(
        [
            html.Span("Atlas is thinking", className="typing-text"),
            html.Span("···", className="typing-dots"),
        ],
        className="msg a typing",
    )


def _empty_itinerary() -> html.Div:
    return html.Div(
        [
            html.P("✨ Your itinerary will appear here"),
            html.P(
                "Start by typing a trip request in the chat — "
                'e.g. "Plan a 5-day trip to Kyoto"'
            ),
        ],
        className="empty-state",
    )


def _empty_sidebar() -> list:
    return [
        html.Div(
            html.P(
                "Trip details and budget summary will appear here.",
                style={"color": "var(--muted)", "fontSize": "12px"},
            ),
            className="sidebar-section",
        )
    ]


# ── Main chat callback ──────────────────────────────────────────────


# ── Phase 1: Clientside — instant user message + typing indicator ────
# Runs in the browser (JavaScript), so the DOM updates immediately
# before the slow server-side agent callback fires.

dash.clientside_callback(
    """
    function(n_clicks, n_submit, userInput, currentChildren, sessionId) {
        if (!userInput || !userInput.trim()) {
            return [
                dash_clientside.no_update,
                dash_clientside.no_update,
                dash_clientside.no_update,
                dash_clientside.no_update
            ];
        }

        var message = userInput.trim();

        // Format timestamp
        var now = new Date();
        var h = now.getUTCHours(), m = now.getUTCMinutes();
        var ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        var ts = h + ':' + (m < 10 ? '0' : '') + m + ' ' + ampm;

        // Build user message bubble
        var userMsg = {
            type: 'Div',
            namespace: 'dash_html_components',
            props: {
                children: [
                    message,
                    {
                        type: 'Div',
                        namespace: 'dash_html_components',
                        props: { children: ts, className: 'ts' }
                    }
                ],
                className: 'msg u'
            }
        };

        // Build typing indicator
        var typing = {
            type: 'Div',
            namespace: 'dash_html_components',
            props: {
                children: [
                    {
                        type: 'Span',
                        namespace: 'dash_html_components',
                        props: { children: 'Atlas is thinking', className: 'typing-text' }
                    },
                    {
                        type: 'Span',
                        namespace: 'dash_html_components',
                        props: { children: '···', className: 'typing-dots' }
                    }
                ],
                className: 'msg a typing'
            }
        };

        // Filter existing children — remove old typing indicators and empty state
        var existing = currentChildren || [];
        if (Array.isArray(existing) && existing.length === 1 &&
            existing[0] && existing[0].props &&
            existing[0].props.className === 'empty-state') {
            existing = [];
        }
        var bubbles = existing.filter(function(c) {
            return !(c && c.props && c.props.className &&
                     c.props.className.indexOf('typing') !== -1);
        });

        bubbles.push(userMsg);
        bubbles.push(typing);

        return [
            bubbles,
            '',
            { message: message, session_id: sessionId },
            '⏳ Thinking…'
        ];
    }
    """,
    Output("chat-display", "children"),
    Output("user-input", "value"),
    Output("pending-msg-store", "data"),
    Output("status-bar", "children"),
    Input("send-btn", "n_clicks"),
    Input("user-input", "n_submit"),
    State("user-input", "value"),
    State("chat-display", "children"),
    State("session-id-store", "data"),
    prevent_initial_call=True,
)


# ── Phase 2: Agent call — process message and update all panels ─────


@callback(
    Output("chat-display", "children", allow_duplicate=True),
    Output("itinerary-display", "children"),
    Output("itinerary-header", "children"),
    Output("sidebar-display", "children"),
    Output("status-bar", "children", allow_duplicate=True),
    Output("loading-trigger", "children"),
    Output("pending-msg-store", "data", allow_duplicate=True),
    Input("pending-msg-store", "data"),
    State("session-id-store", "data"),
    prevent_initial_call=True,
)
def handle_agent_response(pending, session_id):
    """Call the agent and update all panels once the response arrives."""
    if not pending or not isinstance(pending, dict) or "message" not in pending:
        raise PreventUpdate

    user_input = pending["message"]
    sid = pending.get("session_id", session_id)

    try:
        request = ChatRequest(message=user_input, session_id=sid)
        response = handle_chat(request)

        # Render chat bubbles from the authoritative session history.
        history = get_chat_history(sid)
        chat_bubbles = [_render_message(m["role"], m["content"]) for m in history]

        # Render itinerary panel — use structured rendering if available.
        # If the structured model is missing, attempt a second-chance
        # parse from the raw Markdown / reply text before falling back.
        itinerary_obj = response.itinerary
        if itinerary_obj is None:
            for candidate in (response.itinerary_md, response.reply):
                if candidate and isinstance(candidate, str) and candidate.strip():
                    try:
                        itinerary_obj = parse_agent_result(candidate)
                        logger.info("Second-chance parsing succeeded.")
                        break
                    except Exception:
                        continue

        if itinerary_obj:
            itinerary_content = render_itinerary(itinerary_obj)
            header_text = render_itinerary_header(itinerary_obj)
            sidebar_content = render_sidebar(itinerary_obj)
        elif response.itinerary_md:
            # Markdown fallback: strip any leading JSON blobs and
            # render with proper formatting.
            md_text = response.itinerary_md.strip()
            # If the "markdown" is actually raw JSON, wrap it nicely
            if md_text.startswith("{") or md_text.startswith("["):
                itinerary_content = html.Div(
                    [
                        html.Div(
                            [
                                html.P(
                                    "📋 The itinerary was generated but couldn't "
                                    "be fully structured. Here's the raw plan:"
                                ),
                            ],
                            style={
                                "padding": "12px",
                                "backgroundColor": "var(--bg3)",
                                "borderRadius": "8px",
                                "marginBottom": "12px",
                            },
                        ),
                        dash.dcc.Markdown(
                            f"```json\n{md_text}\n```",
                            style={"color": "var(--text)", "lineHeight": "1.6"},
                        ),
                    ]
                )
            else:
                itinerary_content = html.Div(
                    dash.dcc.Markdown(
                        md_text,
                        style={"color": "var(--text)", "lineHeight": "1.6"},
                    )
                )
            header_text = "🗺️ Itinerary"
            sidebar_content = _empty_sidebar()
        else:
            # General reply — show as markdown in the itinerary area
            itinerary_content = html.Div(
                dash.dcc.Markdown(
                    response.reply,
                    style={"color": "var(--text)", "lineHeight": "1.6"},
                )
            )
            header_text = "🗺️ Itinerary"
            sidebar_content = _empty_sidebar()

        status = "✅ Itinerary ready" if itinerary_obj else "✅ Response received"

        return (
            chat_bubbles,
            itinerary_content,
            header_text,
            sidebar_content,
            status,
            "",
            None,  # clear pending store
        )

    except Exception as exc:
        logger.error("Chat error: %s\n%s", exc, traceback.format_exc())

        # On error, re-render history (without typing indicator) + error msg.
        try:
            history = get_chat_history(sid)
            chat_bubbles = [_render_message(m["role"], m["content"]) for m in history]
        except Exception:
            chat_bubbles = no_update

        return (
            chat_bubbles,
            no_update,
            no_update,
            no_update,
            f"❌ Error: {exc}",
            "",
            None,  # clear pending store
        )


# ── Activity card expand/collapse ───────────────────────────────────


dash.clientside_callback(
    """
    function(n_clicks, current_class) {
        if (!n_clicks) return dash_clientside.no_update;
        if (current_class && current_class.includes('open')) {
            return current_class.replace(' open', '').replace('open', '');
        }
        return (current_class || '') + ' open';
    }
    """,
    Output({"type": "act-detail", "index": ALL}, "className"),
    Input({"type": "act-toggle", "index": ALL}, "n_clicks"),
    State({"type": "act-detail", "index": ALL}, "className"),
    prevent_initial_call=True,
)


# Rotate the chevron toggle arrow
dash.clientside_callback(
    """
    function(n_clicks, current_class) {
        if (!n_clicks) return dash_clientside.no_update;
        if (current_class && current_class.includes('open')) {
            return current_class.replace(' open', '').replace('open', '');
        }
        return (current_class || '') + ' open';
    }
    """,
    Output({"type": "act-toggle", "index": ALL}, "className"),
    Input({"type": "act-toggle", "index": ALL}, "n_clicks"),
    State({"type": "act-toggle", "index": ALL}, "className"),
    prevent_initial_call=True,
)


# ── Tab switching ───────────────────────────────────────────────────


@callback(
    Output("tab-itinerary", "className"),
    Output("tab-explore", "className"),
    Output("tab-budget", "className"),
    Output("tab-notes", "className"),
    Output("active-tab-store", "data"),
    Input("tab-itinerary", "n_clicks"),
    Input("tab-explore", "n_clicks"),
    Input("tab-budget", "n_clicks"),
    Input("tab-notes", "n_clicks"),
    prevent_initial_call=True,
)
def switch_tab(*_):
    """Highlight the active tab."""
    triggered = ctx.triggered_id or "tab-itinerary"
    tabs = {
        "tab-itinerary": "itinerary",
        "tab-explore": "explore",
        "tab-budget": "budget",
        "tab-notes": "notes",
    }
    active = tabs.get(str(triggered), "itinerary")
    classes = []
    for tid in ["tab-itinerary", "tab-explore", "tab-budget", "tab-notes"]:
        classes.append("tab active" if tabs[tid] == active else "tab")
    classes.append(active)
    return tuple(classes)


# ── Save callback ───────────────────────────────────────────────────


@callback(
    Output("status-bar", "children", allow_duplicate=True),
    Input("save-btn", "n_clicks"),
    State("session-id-store", "data"),
    prevent_initial_call=True,
)
def handle_save_click(n_clicks, session_id):
    """Save the current itinerary to disk."""
    try:
        result = handle_save(session_id)
        return f"💾 Saved to {result.json_path}"
    except ValueError as exc:
        return f"⚠️ {exc}"
    except Exception as exc:
        logger.error("Save error: %s", exc)
        return f"❌ Save failed: {exc}"


# ── Export callback ─────────────────────────────────────────────────


@callback(
    Output("status-bar", "children", allow_duplicate=True),
    Input("export-btn", "n_clicks"),
    State("session-id-store", "data"),
    prevent_initial_call=True,
)
def handle_export_click(n_clicks, session_id):
    """Export the current itinerary as Markdown."""
    try:
        result = handle_export(session_id)
        return f"📥 Exported to {result.markdown_path}"
    except ValueError as exc:
        return f"⚠️ {exc}"
    except Exception as exc:
        logger.error("Export error: %s", exc)
        return f"❌ Export failed: {exc}"


# ── Model badge ─────────────────────────────────────────────────────


@callback(
    Output("model-badge", "children"),
    Input("session-id-store", "data"),
)
def update_model_badge(_):
    """Display the current LLM model in the navbar."""
    try:
        settings = get_settings()
        return settings.atlas_llm_model
    except Exception:
        return "unknown"


# ── Profile modal open/close ────────────────────────────────────────


@callback(
    Output("profile-modal", "className"),
    Output("profile-trip-count", "children"),
    Output("profile-updated-at", "children"),
    Output("profile-dest-types", "children"),
    Output("profile-categories", "children"),
    Output("profile-pace", "value"),
    Output("profile-budget", "value"),
    Output("profile-past-dests", "children"),
    Input("profile-btn", "n_clicks"),
    Input("profile-close-btn", "n_clicks"),
    Input("profile-cancel-btn", "n_clicks"),
    Input("profile-save-btn", "n_clicks"),
    State("profile-modal", "className"),
    State("profile-pace", "value"),
    State("profile-budget", "value"),
    State("profile-dest-type-input", "value"),
    State("profile-category-input", "value"),
    prevent_initial_call=True,
)
def toggle_profile_modal(
    open_clicks,
    close_clicks,
    cancel_clicks,
    save_clicks,
    current_class,
    pace_value,
    budget_value,
    dest_type_input,
    category_input,
):
    """Open/close the profile modal and handle save."""
    triggered = ctx.triggered_id

    # Close actions
    if triggered in ("profile-close-btn", "profile-cancel-btn"):
        return ("modal-overlay",) + (no_update,) * 7

    # Save action
    if triggered == "profile-save-btn":
        profile = load_profile()
        if pace_value:
            profile.preferred_pace = pace_value
        if budget_value is not None:
            profile.typical_budget_usd = float(budget_value)
        profile.updated_at = datetime.now(timezone.utc)
        save_profile(profile)
        return ("modal-overlay",) + (no_update,) * 7

    # Open action — load profile data
    if triggered == "profile-btn":
        profile = load_profile()

        dest_tags = [
            html.Span(
                [t, html.Span(" ×", className="rm")],
                className="tag-ed",
            )
            for t in profile.favourite_destination_types
        ] or [html.Span("None yet", style={"color": "var(--dim)", "fontSize": "11px"})]

        cat_tags = [
            html.Span(
                [c, html.Span(" ×", className="rm")],
                className="tag-ed",
            )
            for c in profile.favourite_categories
        ] or [html.Span("None yet", style={"color": "var(--dim)", "fontSize": "11px"})]

        past_tags = [
            html.Span(d, className="tag-ed") for d in profile.past_destinations
        ] or [html.Span("None yet", style={"color": "var(--dim)", "fontSize": "11px"})]

        updated = (
            profile.updated_at.strftime("%b %d, %Y") if profile.updated_at else "Never"
        )

        return (
            "modal-overlay active",
            str(profile.trip_count),
            updated,
            dest_tags,
            cat_tags,
            (
                profile.preferred_pace.value
                if hasattr(profile.preferred_pace, "value")
                else profile.preferred_pace
            ),
            profile.typical_budget_usd or 150,
            past_tags,
        )

    raise PreventUpdate
