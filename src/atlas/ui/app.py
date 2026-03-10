"""Atlas Dash application entry point.

Run with::

    python -m atlas.ui.app

Or programmatically::

    from atlas.ui.app import create_app
    app = create_app()
    app.run(debug=True)
"""

from __future__ import annotations

import dash

from atlas.ui.layout import create_layout


def create_app() -> dash.Dash:
    """Create and configure the Atlas Dash application."""
    app = dash.Dash(
        __name__,
        title="Atlas Travel Assistant",
        update_title="Atlas — thinking…",
        suppress_callback_exceptions=True,
    )

    app.layout = create_layout()

    # Import callbacks to register them (side-effect import).
    from atlas.ui import callbacks as _callbacks  # noqa: F401

    return app


# ── CLI entry point ─────────────────────────────────────────────────
if __name__ == "__main__":
    from atlas.config import get_settings

    settings = get_settings()
    app = create_app()
    app.run(
        host=settings.atlas_host,
        port=settings.atlas_port,
        debug=settings.atlas_debug,
    )
