"""FastAPI HTTP layer for the Next.js frontend.

The new web frontend (``web/``) talks to this server.  Routes are thin
wrappers around :mod:`atlas.api.handlers` and the domain layer; no LLM
calls happen here.

Run with::

    uv run atlas-api
    # or
    python -m atlas.api.server
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from atlas.api.routes import chat, itinerary, profile, stream

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the Atlas FastAPI application."""
    app = FastAPI(
        title="Atlas Travel Assistant API",
        version="0.1.0",
        description=(
            "REST + SSE API consumed by the Atlas Next.js frontend. "
            "Wraps the existing handlers in atlas.api.handlers."
        ),
    )

    # Allow the Next.js dev server (and a couple of common alternates) to
    # call the API from the browser.  Tighten in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat.router, prefix="/api", tags=["chat"])
    app.include_router(itinerary.router, prefix="/api", tags=["itinerary"])
    app.include_router(profile.router, prefix="/api", tags=["profile"])
    app.include_router(stream.router, prefix="/api", tags=["stream"])

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def main() -> None:
    """CLI entry point — ``uv run atlas-api``."""
    import uvicorn

    from atlas.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "atlas.api.server:app",
        host=settings.atlas_host,
        port=8000,
        reload=settings.atlas_debug,
    )


if __name__ == "__main__":
    main()
