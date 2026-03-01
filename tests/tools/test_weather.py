"""Tests for the weather tool (``atlas.tools.weather``)."""

from __future__ import annotations


def test_get_weather_no_api_key(monkeypatch) -> None:
    """Without an API key, the tool returns a graceful error dict."""
    monkeypatch.setenv("ATLAS_WEATHER_API_KEY", "")

    from atlas.config import get_settings

    get_settings.cache_clear()

    from atlas.tools.weather import get_weather

    result = get_weather.invoke({"city": "Kyoto", "date": "2025-04-01"})
    assert "error" in result
    assert result["city"] == "Kyoto"


def test_get_weather_placeholder_response(monkeypatch) -> None:
    """With an API key, the placeholder returns structured data."""
    monkeypatch.setenv("ATLAS_WEATHER_API_KEY", "fake-key")

    from atlas.config import get_settings

    get_settings.cache_clear()

    from atlas.tools.weather import get_weather

    result = get_weather.invoke({"city": "Tokyo", "date": "2025-04-05"})
    assert result["city"] == "Tokyo"
    assert result["date"] == "2025-04-05"
    assert "note" in result  # placeholder note
