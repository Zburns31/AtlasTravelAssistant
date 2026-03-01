"""Destination search tool — discover places matching a query.

Designed to be called by the LangChain agent via tool-calling.  Uses
``httpx`` for HTTP so it can be mocked in tests without live APIs.
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool


@tool
def search_destinations(query: str, max_results: int = 5) -> list[dict]:
    """Search for travel destinations matching *query*.

    Returns a list of dicts, each with ``name``, ``country``,
    ``description``, and ``coordinates`` (lat, lon).

    Parameters
    ----------
    query
        Free-text search term (e.g. "temples in Kyoto", "beach towns
        in Portugal").
    max_results
        Maximum number of results to return (default 5).
    """
    # TODO: Integrate a real destination / POI API (e.g. Amadeus, Google
    #       Places, or a curated dataset).  Placeholder returns an empty
    #       list so the agent can handle "no results" gracefully.
    try:
        # Placeholder — swap for real endpoint:
        # resp = httpx.get(
        #     "https://api.example.com/destinations",
        #     params={"q": query, "limit": max_results},
        #     timeout=10,
        # )
        # resp.raise_for_status()
        # return resp.json()["results"]
        return [
            {
                "name": query.title(),
                "country": "Unknown",
                "description": f"Search results for '{query}' — integration pending.",
                "coordinates": None,
                "note": "Destination search integration pending — placeholder data.",
            }
        ]
    except httpx.HTTPStatusError as exc:
        return [{"error": f"Search API returned {exc.response.status_code}."}]
    except httpx.RequestError as exc:
        return [{"error": f"Search API request failed: {exc}"}]
