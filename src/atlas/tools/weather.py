"""Weather tool — fetch historical temperature data for a destination and date range.

Uses two free, no-API-key-required services:

* **Nominatim** (OpenStreetMap) for geocoding city names → coordinates
* **Open-Meteo Archive API** for historical hourly temperature data (1940–present)

The agent calls ``get_weather`` with a city and trip date range and receives
per-day temperature summaries (morning, afternoon, evening averages plus
daily high/low) to inform itinerary recommendations.

Designed to be called by the LangChain agent via tool-calling.  All HTTP is
done via ``httpx`` so it can be cleanly mocked in tests.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
from langchain_core.tools import tool

# ── Constants ────────────────────────────────────────────────────────────────

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

_USER_AGENT = "AtlasTravelAssistant/0.1 (https://github.com/atlas-travel-assistant)"

# Hour ranges used to bucket temperatures into time-of-day averages.
_MORNING_HOURS = range(6, 12)  # 06:00–11:00
_AFTERNOON_HOURS = range(12, 18)  # 12:00–17:00
_EVENING_HOURS = range(18, 22)  # 18:00–21:00


# ── Internal helpers ─────────────────────────────────────────────────────────

# In-process caches to avoid duplicate geocoding / weather API calls within
# the same agent run.  Cleared between runs if needed via the public helpers.
_geocode_cache: dict[tuple, dict] = {}
_weather_cache: dict[tuple, dict] = {}


def clear_weather_caches() -> None:
    """Reset geocode and weather response caches."""
    _geocode_cache.clear()
    _weather_cache.clear()


def _geocode_city(
    city: str,
    *,
    state: str = "",
    country_code: str = "",
) -> dict:
    """Resolve *city* to ``{name, lat, lon}`` via the Nominatim API.

    Results are cached in-process (city names are deterministic).
    """
    cache_key = (city, state, country_code)
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]
    query = city
    if state:
        query += f", {state}"
    if country_code:
        query += f", {country_code}"

    params: dict = {
        "q": query,
        "format": "json",
        "limit": 1,
    }
    if country_code:
        params["countrycodes"] = country_code.lower()

    resp = httpx.get(
        NOMINATIM_URL,
        params=params,
        headers={"User-Agent": _USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()

    if not results:
        raise ValueError(f"No location found for: {query}")

    hit = results[0]
    result = {
        "name": hit.get("display_name", city),
        "lat": float(hit["lat"]),
        "lon": float(hit["lon"]),
    }
    _geocode_cache[cache_key] = result
    return result


def _fetch_hourly_temperatures(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    *,
    temperature_unit: str = "fahrenheit",
) -> dict:
    """Fetch hourly temperatures from the Open-Meteo Archive API.

    Results are cached in-process (historical weather data is immutable).
    """
    cache_key = (lat, lon, start_date, end_date, temperature_unit)
    if cache_key in _weather_cache:
        return _weather_cache[cache_key]

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "temperature_2m",
        "temperature_unit": temperature_unit,
        "timezone": "auto",
    }

    resp = httpx.get(OPEN_METEO_URL, params=params, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    _weather_cache[cache_key] = result
    return result


def _avg(values: list[float | None]) -> float | None:
    """Return the average of non-None values, or None if empty."""
    nums = [v for v in values if v is not None]
    return round(sum(nums) / len(nums), 1) if nums else None


def _build_daily_summaries(
    api_response: dict,
    temperature_unit: str = "fahrenheit",
) -> list[dict]:
    """Group hourly temperatures into per-day summaries.

    Each day includes:
    - ``temp_high`` / ``temp_low`` — daily extremes
    - ``temp_morning_avg`` — average 06:00–11:00
    - ``temp_afternoon_avg`` — average 12:00–17:00
    - ``temp_evening_avg`` — average 18:00–21:00
    - ``temp_unit`` — ``"fahrenheit"`` or ``"celsius"``
    """
    hourly = api_response.get("hourly", {})
    times: list[str] = hourly.get("time", [])
    temps: list[float | None] = hourly.get("temperature_2m", [])
    unit = temperature_unit

    # Group by date.
    days_map: dict[str, list[tuple[int, float | None]]] = {}
    for ts, temp in zip(times, temps):
        # ts format: "2025-04-01T06:00"
        day_str = ts[:10]
        hour = int(ts[11:13])
        days_map.setdefault(day_str, []).append((hour, temp))

    summaries: list[dict] = []
    for day_str in sorted(days_map):
        entries = days_map[day_str]
        all_temps = [t for _, t in entries if t is not None]

        morning = [t for h, t in entries if h in _MORNING_HOURS and t is not None]
        afternoon = [t for h, t in entries if h in _AFTERNOON_HOURS and t is not None]
        evening = [t for h, t in entries if h in _EVENING_HOURS and t is not None]

        summaries.append(
            {
                "date": day_str,
                "temp_high": round(max(all_temps), 1) if all_temps else None,
                "temp_low": round(min(all_temps), 1) if all_temps else None,
                "temp_morning_avg": _avg(morning),
                "temp_afternoon_avg": _avg(afternoon),
                "temp_evening_avg": _avg(evening),
                "temp_unit": unit,
            }
        )
    return summaries


# ── LangChain tool ───────────────────────────────────────────────────────────


@tool
def get_weather(
    city: str,
    start_date: str,
    end_date: str,
    temperature_unit: str = "fahrenheit",
) -> dict:
    """Get daily temperature summaries for *city* from *start_date* to *end_date*.

    Both dates are inclusive and must be in ``YYYY-MM-DD`` format.
    Data comes from the Open-Meteo historical archive (free, no API key).

    Returns a dict with:
    - ``city`` — the queried city name
    - ``location`` — resolved display name, latitude, longitude
    - ``start_date`` / ``end_date`` — the requested range
    - ``days`` — list of per-day summaries, each containing:
        ``date``, ``temp_high``, ``temp_low``,
        ``temp_morning_avg`` (06–11h), ``temp_afternoon_avg`` (12–17h),
        ``temp_evening_avg`` (18–21h), ``temp_unit``

    Parameters
    ----------
    city
        City name, e.g. ``"Kyoto"`` or ``"Chicago, Illinois, US"``.
    start_date
        Trip start date (``YYYY-MM-DD``).
    end_date
        Trip end date (``YYYY-MM-DD``), inclusive.
    temperature_unit
        ``"fahrenheit"`` (default) or ``"celsius"``.
    """
    # Validate the date range.
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except ValueError:
        return {
            "city": city,
            "error": (
                f"Invalid date format — expected YYYY-MM-DD, "
                f"got start_date={start_date!r}, end_date={end_date!r}."
            ),
        }

    if ed < sd:
        return {
            "city": city,
            "error": "end_date must be on or after start_date.",
        }

    # Cap at 30 days to avoid oversized API responses.
    if (ed - sd).days > 30:
        ed = sd + timedelta(days=30)
        end_date = ed.isoformat()

    try:
        location = _geocode_city(city)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        return {
            "city": city,
            "error": f"Geocoding failed for '{city}': {exc}",
        }
    except ValueError as exc:
        return {"city": city, "error": str(exc)}

    try:
        raw = _fetch_hourly_temperatures(
            location["lat"],
            location["lon"],
            start_date,
            end_date,
            temperature_unit=temperature_unit,
        )
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        return {
            "city": city,
            "location": location,
            "error": f"Weather API request failed: {exc}",
        }

    days = _build_daily_summaries(raw, temperature_unit=temperature_unit)

    return {
        "city": city,
        "location": location,
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
    }


# ── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("--- Weather for Chicago (Jul 1–4, 2024) ---")
    result = get_weather.invoke(
        {
            "city": "Chicago, Illinois, US",
            "start_date": "2024-07-01",
            "end_date": "2024-07-04",
        }
    )
    loc = result.get("location", {})
    print(f"Location: {loc.get('name')}")
    print(f"Coords:   {loc.get('lat')}, {loc.get('lon')}")
    print()
    for day in result.get("days", []):
        print(
            f"  {day['date']}  "
            f"High {day['temp_high']}  Low {day['temp_low']}  "
            f"Morning {day['temp_morning_avg']}  "
            f"Afternoon {day['temp_afternoon_avg']}  "
            f"Evening {day['temp_evening_avg']}  "
            f"({day['temp_unit']})"
        )

    print()
    print("--- Weather for Kyoto (Apr 10–12, 2024, Celsius) ---")
    result = get_weather.invoke(
        {
            "city": "Kyoto",
            "start_date": "2024-04-10",
            "end_date": "2024-04-12",
            "temperature_unit": "celsius",
        }
    )
    print(json.dumps(result, indent=2))
