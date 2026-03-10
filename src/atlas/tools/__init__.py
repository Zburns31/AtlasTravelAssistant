"""Atlas tool registry.

Every ``@tool``-decorated function that the agent can call is collected
into ``ALL_TOOLS`` so the agent graph always gets the full set.

Itinerary save/export are **not** LLM tools — they live in
``atlas.domain.itinerary`` and are triggered by user actions or
called automatically when content is ready for display.

Usage:
    from atlas.tools import ALL_TOOLS
"""

from atlas.tools.search import search_places, search_web
from atlas.tools.weather import get_weather

ALL_TOOLS = [
    search_web,
    search_places,
    get_weather,
]
