"""Atlas tool registry.

Every ``@tool``-decorated function that the agent can call is collected
into ``ALL_TOOLS`` so the agent graph always gets the full set.

Usage:
    from atlas.tools import ALL_TOOLS
"""

from atlas.tools.search import search_places, search_web
from atlas.tools.weather import get_weather

# Tools added below as they are implemented.
# Itinerary and profile tools will be added in later phases.
ALL_TOOLS = [
    search_web,
    search_places,
    get_weather,
]
