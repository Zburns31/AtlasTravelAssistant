"""Backward-compatible shim — profile persistence moved to ``atlas.domain.profile``.

Kept so existing Dash callbacks (``atlas.ui.callbacks``) continue to work
during the transition to the Next.js frontend.  New code should import
from ``atlas.domain.profile`` directly.
"""

from __future__ import annotations

from atlas.domain.profile import (
    PROFILE_DIR,
    PROFILE_PATH,
    load_profile,
    save_profile,
)

__all__ = ["PROFILE_DIR", "PROFILE_PATH", "load_profile", "save_profile"]
