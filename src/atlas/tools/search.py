"""Search tools — web search and places lookup via Serper (Google Search API).

Uses `Serper.dev <https://serper.dev>`_ to provide two capabilities:

* **search_web** — organic Google web results for general travel research
* **search_places** — structured Google Places data (ratings, addresses,
  coordinates) for POI / attraction discovery

Both tools require a ``SERPER_API_KEY`` environment variable (2 500 free
queries at sign-up, no credit card needed).

All HTTP is done via ``httpx`` so it can be cleanly mocked in tests.
"""

from __future__ import annotations

import logging

import httpx
from langchain_core.tools import tool

from atlas.config import get_settings
from atlas.tools.fetch import fetch_page_content

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_PLACES_URL = "https://google.serper.dev/places"


# ── Internal helpers ─────────────────────────────────────────────────────────

# In-process cache keyed on (url, frozen_payload) to avoid duplicate Serper
# calls within the same agent run.  Cleared between runs if needed via
# ``clear_serper_cache()``.
_serper_cache: dict[tuple, dict] = {}


def clear_serper_cache() -> None:
    """Reset the in-process Serper response cache."""
    _serper_cache.clear()


def _get_api_key() -> str:
    """Return the Serper API key or raise if not configured."""
    key = get_settings().serper_api_key
    if not key:
        raise ValueError(
            "SERPER_API_KEY is not set. "
            "Get a free key at https://serper.dev and add it to your .env file."
        )
    return key


def _serper_request(url: str, payload: dict) -> dict:
    """Make an authenticated POST request to Serper and return JSON.

    Results are cached in-process so the same query within a single
    agent run does not hit the API twice.
    """
    cache_key = (url, tuple(sorted(payload.items())))
    if cache_key in _serper_cache:
        return _serper_cache[cache_key]

    resp = httpx.post(
        url,
        json=payload,
        headers={
            "X-API-KEY": _get_api_key(),
            "Content-Type": "application/json",
        },
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()
    _serper_cache[cache_key] = result
    return result


# ── LangChain tools ─────────────────────────────────────────────────────────


@tool
def search_web(query: str, num_results: int = 5) -> dict:
    """Search the web for travel-related information.

    Returns organic Google search results including titles, snippets,
    links, and **extracted page content** for the top results, plus a
    knowledge-graph summary when available.

    The ``page_content`` field on the top results contains the full
    main-body text of the page (up to ~8 000 chars), so you usually
    do **not** need to fetch pages separately.

    Use broad, comprehensive queries to minimise the number of calls
    (e.g. ``"Kyoto travel guide temples restaurants budget tips"``).

    Parameters
    ----------
    query
        Free-text search (e.g. ``"best temples to visit in Kyoto April"``).
    num_results
        Number of organic results to return (default 10, max 10).
    """
    num_results = max(1, min(num_results, 10))

    try:
        raw = _serper_request(
            SERPER_SEARCH_URL,
            {"q": query, "num": num_results},
        )
    except ValueError as exc:
        return {"query": query, "error": str(exc)}
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        return {"query": query, "error": f"Search API request failed: {exc}"}

    # Extract the pieces useful to the agent.
    organic = [
        {
            "title": r.get("title", ""),
            "link": r.get("link", ""),
            "snippet": r.get("snippet", ""),
            "position": r.get("position"),
        }
        for r in raw.get("organic", [])
    ]

    # ── Auto-fetch page content for top N results ────────────────────
    fetch_top_n = get_settings().atlas_fetch_top_n
    for item in organic[:fetch_top_n]:
        link = item.get("link", "")
        if link:
            content = fetch_page_content(link)
            if content:
                item["page_content"] = content

    result: dict = {"query": query, "results": organic}

    # Include knowledge graph when present (often has a useful summary).
    kg = raw.get("knowledgeGraph")
    if kg:
        result["knowledgeGraph"] = {
            "title": kg.get("title", ""),
            "type": kg.get("type", ""),
            "description": kg.get("description", ""),
            "website": kg.get("website", ""),
            "imageUrl": kg.get("imageUrl", ""),
            "attributes": kg.get("attributes", {}),
        }

    return result


@tool
def search_places(query: str, num_results: int = 5) -> dict:
    """Search for places, attractions, and points of interest.

    Returns structured Google Places data including name, address,
    rating, review count, and GPS coordinates — ideal for building
    itinerary activities with real locations.

    Parameters
    ----------
    query
        Place search (e.g. ``"top restaurants in Rome"``,
        ``"museums near Central Park NYC"``).
    num_results
        Number of place results to return (default 8, max 10).
    """
    num_results = max(1, min(num_results, 10))

    try:
        raw = _serper_request(
            SERPER_PLACES_URL,
            {"q": query, "num": num_results},
        )
    except ValueError as exc:
        return {"query": query, "error": str(exc)}
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        return {"query": query, "error": f"Places API request failed: {exc}"}

    places = [
        {
            "title": p.get("title", ""),
            "address": p.get("address", ""),
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "rating": p.get("rating"),
            "review_count": p.get("ratingCount"),
            "category": p.get("category", ""),
            "phone": p.get("phoneNumber", ""),
            "website": p.get("website", ""),
            "cid": p.get("cid", ""),
        }
        for p in raw.get("places", [])
    ]

    return {"query": query, "places": places}


# ── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("--- Web search: 'best temples in Kyoto' ---")
    result = search_web.invoke({"query": "best temples in Kyoto", "num_results": 3})
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        for r in result.get("results", []):
            print(f"  [{r['position']}] {r['title']}")
            print(f"      {r['link']}")
            print(f"      {r['snippet'][:100]}...")
            print()
        kg = result.get("knowledgeGraph")
        if kg:
            print(f"  Knowledge Graph: {kg['title']} — {kg['type']}")
            print(f"      {kg['description'][:120]}...")

    print()
    print("--- Places search: 'top restaurants in Rome' ---")
    result = search_places.invoke(
        {"query": "top restaurants in Rome", "num_results": 3}
    )
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        for p in result.get("places", []):
            print(f"  {p['title']}  ★{p['rating']}  ({p['review_count']} reviews)")
            print(f"      {p['address']}")
            print(f"      ({p['latitude']}, {p['longitude']})  {p['category']}")
            print()
