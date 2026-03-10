"""Profile persistence — load/save UserProfile from ~/.atlas/.

The profile modal reads and writes this file so preferences survive
across sessions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from atlas.domain.models import UserProfile

logger = logging.getLogger(__name__)

PROFILE_DIR = Path.home() / ".atlas"
PROFILE_PATH = PROFILE_DIR / "user_profile.json"


def load_profile() -> UserProfile:
    """Load the user profile from disk, returning defaults if missing."""
    try:
        if PROFILE_PATH.exists():
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            return UserProfile(**data)
    except Exception as exc:
        logger.warning("Could not load profile: %s", exc)
    return UserProfile()


def save_profile(profile: UserProfile) -> None:
    """Persist the user profile to disk."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(
        profile.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info("Saved profile to %s", PROFILE_PATH)
