"""LLM Router — returns a LangChain ``BaseChatModel`` backed by LiteLLM.

All LLM access in Atlas flows through ``get_llm()``.  The active model is
controlled entirely by environment variables — switching from GPT-4o to
Claude 3.5 Sonnet is a one-line change in ``.env``, not a code change.

LiteLLM provides a unified Python interface for 100+ providers.  Set the
relevant provider's API key (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``,
``GROQ_API_KEY``, etc.) and LiteLLM handles the rest.

When Langfuse credentials are present (``LANGFUSE_PUBLIC_KEY`` +
``LANGFUSE_SECRET_KEY``), all LLM calls are automatically traced for
observability — token usage, latency, cost, and full request/response logs.
"""

from __future__ import annotations

from functools import lru_cache

import litellm
from langchain_litellm import ChatLiteLLM
from langchain_core.language_models import BaseChatModel

from atlas.config import get_settings


def _configure_langfuse() -> None:
    """Enable Langfuse tracing when both public and secret keys are present.

    This configures LiteLLM's native callback system — no extra packages
    beyond ``litellm`` itself are needed (``langfuse`` is installed as a
    dependency).  When keys are absent the function is a silent no-op.
    """
    cfg = get_settings()
    if cfg.langfuse_public_key and cfg.langfuse_secret_key:
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Return a cached ``BaseChatModel`` instance powered by LiteLLM.

    The model is determined by ``ATLAS_LLM_MODEL`` using the LiteLLM
    ``<provider>/<model>`` format (e.g. ``openai/gpt-4o``,
    ``anthropic/claude-3-5-sonnet``, ``groq/llama-3.3-70b-versatile``).

    The corresponding provider API key must be set as an environment
    variable (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, ``GROQ_API_KEY``,
    etc.) — LiteLLM resolves these automatically.

    Returns
    -------
    BaseChatModel
        A LangChain chat model ready for ``.invoke()``, ``.stream()``,
        or binding to a tool-calling agent.
    """
    cfg = get_settings()

    _configure_langfuse()

    return ChatLiteLLM(
        model=cfg.atlas_llm_model,
        temperature=cfg.atlas_llm_temperature,
    )
