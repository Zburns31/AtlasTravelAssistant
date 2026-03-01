"""LLM Router — returns a LangChain ``BaseChatModel`` backed by OpenRouter.

All LLM access in Atlas flows through ``get_llm()``.  The active model is
controlled entirely by environment variables — switching from GPT-4o to
Claude 3.5 Sonnet is a one-line change in ``.env``, not a code change.

OpenRouter provides a single OpenAI-compatible REST endpoint for 300+
models, so only ``langchain-openai`` is needed as a dependency.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from atlas.config import get_settings


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Return a cached ``BaseChatModel`` instance pointed at OpenRouter.

    The model is determined by ``ATLAS_LLM_MODEL`` (e.g. ``openai/gpt-4o``,
    ``anthropic/claude-3-5-sonnet``, ``google/gemini-2.0-flash``).

    Returns
    -------
    BaseChatModel
        A LangChain chat model ready for ``.invoke()``, ``.stream()``,
        or binding to a tool-calling agent.
    """
    cfg = get_settings()

    return ChatOpenAI(
        model=cfg.atlas_llm_model,
        api_key=cfg.openrouter_api_key,
        base_url=cfg.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://github.com/atlas-travel-assistant",
            "X-Title": "Atlas Travel Assistant",
        },
    )
