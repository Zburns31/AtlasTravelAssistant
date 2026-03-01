"""Tests for the search tool (``atlas.tools.search``)."""

from __future__ import annotations


def test_search_destinations_returns_list() -> None:
    """The placeholder should return a non-empty list of dicts."""
    from atlas.tools.search import search_destinations

    result = search_destinations.invoke({"query": "temples in Kyoto"})
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "name" in result[0]


def test_search_destinations_max_results() -> None:
    """``max_results`` should be accepted as a parameter."""
    from atlas.tools.search import search_destinations

    result = search_destinations.invoke({"query": "beaches in Bali", "max_results": 3})
    assert isinstance(result, list)
