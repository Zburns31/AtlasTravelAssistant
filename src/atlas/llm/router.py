"""LLM Router — returns a LangChain ``BaseChatModel`` via LiteLLM.

All LLM access in Atlas flows through ``get_llm()``, which returns a single
``ChatLiteLLM`` instance.  LiteLLM infers the provider from the model string
prefix (e.g. ``openrouter/``, ``groq/``, ``gemini/``) and reads the matching
API key from environment variables automatically.

Example ``ATLAS_LLM_MODEL`` values:

* ``openrouter/google/gemini-3-flash-preview`` → OpenRouter (``OPENROUTER_API_KEY``)
* ``groq/llama-3.3-70b-versatile``             → Groq      (``GROQ_API_KEY``)
* ``gemini/gemini-2.5-flash``                   → Google    (``GEMINI_API_KEY``)
* ``openai/gpt-4o``                             → OpenAI    (``OPENAI_API_KEY``)
* ``anthropic/claude-3-5-sonnet``               → Anthropic (``ANTHROPIC_API_KEY``)

When Langfuse credentials are present (``LANGFUSE_PUBLIC_KEY`` +
``LANGFUSE_SECRET_KEY``), all LLM calls are automatically traced for
observability via LangChain's callback system.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from atlas.config import get_settings

logger = logging.getLogger(__name__)

# Tracks the wall-clock time of the last LLM call so we can enforce
# a minimum inter-call delay (see ``throttle_llm_call``).
_last_call_ts: float = 0.0


def _build_langfuse_handler():
    """Return a Langfuse callback handler if credentials are present, else ``None``.

    Langfuse v3 reads ``LANGFUSE_SECRET_KEY`` and ``LANGFUSE_HOST`` from
    environment variables automatically.  We only pass ``public_key``
    explicitly to the constructor.
    """
    cfg = get_settings()
    if cfg.langfuse_public_key and cfg.langfuse_secret_key:
        try:
            from langfuse.langchain import CallbackHandler

            return CallbackHandler(public_key=cfg.langfuse_public_key)
        except Exception:
            return None
    return None


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Return a cached ``ChatLiteLLM`` for the configured model.

    The model is set by ``ATLAS_LLM_MODEL``.  LiteLLM infers the provider
    from the model string prefix and reads the corresponding API key from
    environment variables (e.g. ``GROQ_API_KEY``, ``OPENROUTER_API_KEY``).

    Returns
    -------
    BaseChatModel
        A LangChain chat model ready for ``.invoke()``, ``.stream()``,
        or binding to a tool-calling agent.
    """
    from langchain_litellm import ChatLiteLLM

    cfg = get_settings()

    callbacks: list = []
    langfuse_handler = _build_langfuse_handler()
    if langfuse_handler is not None:
        callbacks.append(langfuse_handler)

    llm = ChatLiteLLM(
        model=cfg.atlas_llm_model,
        temperature=cfg.atlas_llm_temperature,
        max_retries=cfg.atlas_llm_num_retries,
        request_timeout=cfg.atlas_llm_request_timeout,
        callbacks=callbacks or None,
    )

    logger.info("LLM initialised — model=%s", cfg.atlas_llm_model)
    return llm


def throttle_llm_call() -> None:
    """Sleep if needed to enforce ``atlas_llm_call_delay`` between LLM calls.

    Call this **before** every ``llm.invoke()`` in the agent graph.
    The delay is configured via ``ATLAS_LLM_CALL_DELAY`` (default 3 s)
    and helps stay within free-tier RPM quotas (~20 RPM).

    Set ``ATLAS_LLM_CALL_DELAY=0`` to disable throttling.
    """
    global _last_call_ts  # noqa: PLW0603

    cfg = get_settings()
    delay = cfg.atlas_llm_call_delay
    if delay <= 0:
        _last_call_ts = time.monotonic()
        return

    now = time.monotonic()
    elapsed = now - _last_call_ts
    if _last_call_ts > 0 and elapsed < delay:
        wait = delay - elapsed
        logger.debug("Throttling LLM call — sleeping %.2f s", wait)
        time.sleep(wait)

    _last_call_ts = time.monotonic()
