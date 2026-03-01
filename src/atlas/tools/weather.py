"""Weather tool — fetch forecast data for a destination and date.

Designed to be called by the LangChain agent via tool-calling.  The
actual HTTP call uses ``httpx`` so it can be cleanly mocked in tests.
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from atlas.config import get_settings


@tool
def get_weather(city: str, date: str) -> dict:
    """Get the weather forecast for *city* on *date* (YYYY-MM-DD).

    Returns a dict with ``city``, ``date``, ``temp_high_c``,
    ``temp_low_c``, ``conditions``, and ``precipitation_pct``.

    If the weather API key is not configured or the request fails,
    returns a fallback dict indicating data is unavailable so the agent
    can continue without crashing.
    """
    cfg = get_settings()
    api_key = cfg.atlas_weather_api_key

    if not api_key:
        return {
            "city": city,
            "date": date,
            "error": "Weather API key not configured — skipping forecast.",
        }

    # TODO: Replace with real weather API integration (e.g. OpenWeatherMap).
    #       For now, return a structured placeholder so the agent loop works.
    try:
        # Placeholder — swap for real endpoint:
        # resp = httpx.get(
        #     f"https://api.openweathermap.org/data/3.0/onecall",
        #     params={"q": city, "appid": api_key, "units": "metric"},
        #     timeout=10,
        # )
        # resp.raise_for_status()
        # data = resp.json()
        return {
            "city": city,
            "date": date,
            "temp_high_c": None,
            "temp_low_c": None,
            "conditions": "unknown",
            "precipitation_pct": None,
            "note": "Weather integration pending — placeholder data.",
        }
    except httpx.HTTPStatusError as exc:
        return {
            "city": city,
            "date": date,
            "error": f"Weather API returned {exc.response.status_code}.",
        }
    except httpx.RequestError as exc:
        return {
            "city": city,
            "date": date,
            "error": f"Weather API request failed: {exc}",
        }
