"""Itinerary routes — fetch / save / export the current itinerary."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from atlas.api.handlers import (
    get_current_itinerary,
    handle_export,
    handle_save,
)
from atlas.api.schemas import ExportResponse, SaveResponse
from atlas.domain.models import Itinerary

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/itinerary/{session_id}", response_model=Itinerary | None)
def get_itinerary(session_id: str) -> Itinerary | None:
    """Return the latest itinerary for a session, or ``null`` if none."""
    return get_current_itinerary(session_id)


@router.post("/itinerary/{session_id}/save", response_model=SaveResponse)
def post_save(session_id: str) -> SaveResponse:
    """Persist the latest itinerary for ``session_id`` to disk (JSON)."""
    try:
        return handle_save(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Save handler failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/itinerary/{session_id}/export", response_model=ExportResponse)
def post_export(session_id: str) -> ExportResponse:
    """Export the latest itinerary for ``session_id`` as Markdown."""
    try:
        return handle_export(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Export handler failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
