"""Tests for the weather tool (``atlas.tools.weather``)."""

from __future__ import annotations

import httpx
import pytest

from atlas.tools.weather import (
    _avg,
    _build_daily_summaries,
    _geocode_city,
    _fetch_hourly_temperatures,
    get_weather,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

NOMINATIM_RESPONSE = [
    {
        "display_name": "Kyoto, Kyoto Prefecture, Japan",
        "lat": "35.0116",
        "lon": "135.7681",
    }
]


def _make_hourly_response(
    dates: list[str],
    base_temps: list[float] | None = None,
) -> dict:
    """Build a minimal Open-Meteo hourly response for *dates*.

    Each day gets 24 hourly readings.  ``base_temps`` supplies one
    value per day that is offset by the hour index to create variation.
    """
    if base_temps is None:
        base_temps = [60.0] * len(dates)

    times: list[str] = []
    temps: list[float] = []
    for day_str, base in zip(dates, base_temps):
        for hour in range(24):
            times.append(f"{day_str}T{hour:02d}:00")
            # Simple variation: coldest at 04:00, warmest at 14:00.
            offset = -5 + (10 * (1 - abs(hour - 14) / 14))
            temps.append(round(base + offset, 1))

    return {
        "hourly": {"time": times, "temperature_2m": temps},
        "hourly_units": {"temperature_2m": "°F"},
    }


OPEN_METEO_RESPONSE = _make_hourly_response(
    ["2025-04-01", "2025-04-02", "2025-04-03"],
    [60.0, 65.0, 55.0],
)


def _mock_httpx_get(nominatim_json=None, meteo_json=None):
    """Return a side_effect function that routes by URL."""

    def _side_effect(url, **kwargs):
        resp = httpx.Response(200, request=httpx.Request("GET", url))
        if "nominatim" in url:
            resp._content = httpx._content.json_dumps(
                NOMINATIM_RESPONSE if nominatim_json is None else nominatim_json
            )
        elif "open-meteo" in url:
            resp._content = httpx._content.json_dumps(
                OPEN_METEO_RESPONSE if meteo_json is None else meteo_json
            )
        else:
            raise ValueError(f"Unexpected URL: {url}")
        return resp

    return _side_effect


# ── Unit tests: helpers ──────────────────────────────────────────────────────


class TestAvg:
    def test_normal(self) -> None:
        assert _avg([10.0, 20.0, 30.0]) == 20.0

    def test_ignores_none(self) -> None:
        assert _avg([10.0, None, 30.0]) == 20.0

    def test_all_none(self) -> None:
        assert _avg([None, None]) is None

    def test_empty(self) -> None:
        assert _avg([]) is None


class TestBuildDailySummaries:
    def test_produces_correct_count(self) -> None:
        summaries = _build_daily_summaries(OPEN_METEO_RESPONSE)
        assert len(summaries) == 3

    def test_summary_has_expected_keys(self) -> None:
        summaries = _build_daily_summaries(OPEN_METEO_RESPONSE)
        day = summaries[0]
        expected_keys = {
            "date",
            "temp_high",
            "temp_low",
            "temp_morning_avg",
            "temp_afternoon_avg",
            "temp_evening_avg",
            "temp_unit",
        }
        assert set(day.keys()) == expected_keys

    def test_high_gte_low(self) -> None:
        summaries = _build_daily_summaries(OPEN_METEO_RESPONSE)
        for day in summaries:
            assert day["temp_high"] >= day["temp_low"]

    def test_afternoon_warmer_than_morning(self) -> None:
        """Our synthetic data peaks at 14:00, so afternoon > morning."""
        summaries = _build_daily_summaries(OPEN_METEO_RESPONSE)
        for day in summaries:
            assert day["temp_afternoon_avg"] >= day["temp_morning_avg"]

    def test_unit_passthrough(self) -> None:
        summaries = _build_daily_summaries(OPEN_METEO_RESPONSE)
        assert summaries[0]["temp_unit"] == "fahrenheit"

    def test_celsius_unit(self) -> None:
        summaries = _build_daily_summaries(
            OPEN_METEO_RESPONSE, temperature_unit="celsius"
        )
        assert summaries[0]["temp_unit"] == "celsius"

    def test_no_precipitation_or_wind_keys(self) -> None:
        summaries = _build_daily_summaries(OPEN_METEO_RESPONSE)
        day = summaries[0]
        assert "precipitation" not in day
        assert "wind_max_mph" not in day
        assert "conditions" not in day


# ── Unit tests: geocoding ────────────────────────────────────────────────────


class TestGeocodeCity:
    def test_returns_coords(self, mocker) -> None:
        mocker.patch("atlas.tools.weather.httpx.get", side_effect=_mock_httpx_get())
        loc = _geocode_city("Kyoto")
        assert loc["lat"] == pytest.approx(35.0116)
        assert loc["lon"] == pytest.approx(135.7681)
        assert "Kyoto" in loc["name"]

    def test_no_results_raises(self, mocker) -> None:
        mocker.patch(
            "atlas.tools.weather.httpx.get",
            side_effect=_mock_httpx_get(nominatim_json=[]),
        )
        with pytest.raises(ValueError, match="No location found"):
            _geocode_city("Nonexistentville")

    def test_http_error_propagates(self, mocker) -> None:
        def _raise(url, **kw):
            resp = httpx.Response(
                403, request=httpx.Request("GET", url), content=b"Forbidden"
            )
            resp.raise_for_status()

        mocker.patch("atlas.tools.weather.httpx.get", side_effect=_raise)
        with pytest.raises(httpx.HTTPStatusError):
            _geocode_city("Kyoto")


# ── Unit tests: weather fetch ────────────────────────────────────────────────


class TestFetchHourlyTemperatures:
    def test_returns_hourly_data(self, mocker) -> None:
        mocker.patch("atlas.tools.weather.httpx.get", side_effect=_mock_httpx_get())
        raw = _fetch_hourly_temperatures(35.0, 135.7, "2025-04-01", "2025-04-03")
        assert "hourly" in raw
        assert len(raw["hourly"]["time"]) == 3 * 24


# ── Integration tests: the @tool ─────────────────────────────────────────────


class TestGetWeatherTool:
    def test_happy_path(self, mocker) -> None:
        mocker.patch("atlas.tools.weather.httpx.get", side_effect=_mock_httpx_get())
        result = get_weather.invoke(
            {"city": "Kyoto", "start_date": "2025-04-01", "end_date": "2025-04-03"}
        )
        assert result["city"] == "Kyoto"
        assert result["start_date"] == "2025-04-01"
        assert result["end_date"] == "2025-04-03"
        assert len(result["days"]) == 3
        assert result["location"]["lat"] == pytest.approx(35.0116)
        assert "error" not in result
        # Verify per-day temperature fields exist.
        day = result["days"][0]
        assert day["temp_morning_avg"] is not None
        assert day["temp_afternoon_avg"] is not None
        assert day["temp_evening_avg"] is not None

    def test_invalid_date_format(self) -> None:
        result = get_weather.invoke(
            {"city": "Kyoto", "start_date": "not-a-date", "end_date": "2025-04-03"}
        )
        assert "error" in result
        assert "Invalid date" in result["error"]

    def test_end_before_start(self) -> None:
        result = get_weather.invoke(
            {"city": "Kyoto", "start_date": "2025-04-05", "end_date": "2025-04-01"}
        )
        assert "error" in result
        assert "end_date" in result["error"]

    def test_range_capped_at_30_days(self, mocker) -> None:
        mocker.patch("atlas.tools.weather.httpx.get", side_effect=_mock_httpx_get())
        result = get_weather.invoke(
            {"city": "Kyoto", "start_date": "2025-01-01", "end_date": "2025-12-31"}
        )
        assert result["end_date"] == "2025-01-31"
        assert "error" not in result

    def test_geocoding_failure_returns_error(self, mocker) -> None:
        mocker.patch(
            "atlas.tools.weather.httpx.get",
            side_effect=_mock_httpx_get(nominatim_json=[]),
        )
        result = get_weather.invoke(
            {"city": "Fakeville", "start_date": "2025-04-01", "end_date": "2025-04-03"}
        )
        assert "error" in result
        assert "No location found" in result["error"]

    def test_weather_api_failure_returns_error(self, mocker) -> None:
        def _side_effect(url, **kw):
            if "nominatim" in url:
                resp = httpx.Response(200, request=httpx.Request("GET", url))
                resp._content = httpx._content.json_dumps(NOMINATIM_RESPONSE)
                return resp
            resp = httpx.Response(
                500, request=httpx.Request("GET", url), content=b"Server Error"
            )
            resp.raise_for_status()

        mocker.patch("atlas.tools.weather.httpx.get", side_effect=_side_effect)
        result = get_weather.invoke(
            {"city": "Kyoto", "start_date": "2025-04-01", "end_date": "2025-04-03"}
        )
        assert "error" in result
        assert "Weather API" in result["error"]

    def test_celsius_unit_passthrough(self, mocker) -> None:
        mock_get = mocker.patch(
            "atlas.tools.weather.httpx.get", side_effect=_mock_httpx_get()
        )
        get_weather.invoke(
            {
                "city": "Kyoto",
                "start_date": "2025-04-01",
                "end_date": "2025-04-01",
                "temperature_unit": "celsius",
            }
        )
        meteo_call = [c for c in mock_get.call_args_list if "open-meteo" in str(c)]
        assert meteo_call
        assert meteo_call[0].kwargs["params"]["temperature_unit"] == "celsius"
