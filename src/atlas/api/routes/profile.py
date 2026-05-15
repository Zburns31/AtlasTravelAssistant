"""Profile routes — load and persist the user travel profile."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from atlas.domain.models import UserProfile
from atlas.domain.profile import load_profile, save_profile

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/profile", response_model=UserProfile)
def get_profile() -> UserProfile:
    """Return the persisted user profile (defaults if none on disk)."""
    return load_profile()


@router.put("/profile", response_model=UserProfile)
def put_profile(profile: UserProfile) -> UserProfile:
    """Persist the supplied profile and return the saved value."""
    try:
        save_profile(profile)
    except Exception as exc:
        logger.exception("Profile save failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return profile
