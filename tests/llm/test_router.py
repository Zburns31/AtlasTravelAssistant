"""Tests for the LLM router (``atlas.llm.router``)."""

from __future__ import annotations

import litellm
from langchain_core.language_models import BaseChatModel


def test_get_llm_returns_base_chat_model() -> None:
    """``get_llm()`` should return a ``BaseChatModel`` instance."""
    from atlas.llm.router import get_llm

    # Clear cache so we get a fresh instance.
    get_llm.cache_clear()

    llm = get_llm()
    assert isinstance(llm, BaseChatModel)


def test_get_llm_uses_configured_model(monkeypatch) -> None:
    """The router should respect ``ATLAS_LLM_MODEL``."""
    monkeypatch.setenv("ATLAS_LLM_MODEL", "anthropic/claude-3-5-sonnet")

    from atlas.config import get_settings
    from atlas.llm.router import get_llm

    get_settings.cache_clear()
    get_llm.cache_clear()

    llm = get_llm()
    assert llm.model == "anthropic/claude-3-5-sonnet"


def test_get_llm_is_cached() -> None:
    """Successive calls should return the *same* cached instance."""
    from atlas.llm.router import get_llm

    get_llm.cache_clear()

    a = get_llm()
    b = get_llm()
    assert a is b


# ── Langfuse callback tests ────────────────────────────────────────


def test_langfuse_enabled_when_keys_present(monkeypatch) -> None:
    """When both Langfuse keys are set, LiteLLM callbacks should be configured."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    from atlas.config import get_settings
    from atlas.llm.router import get_llm

    get_settings.cache_clear()
    get_llm.cache_clear()

    # Reset callbacks before test
    litellm.success_callback = []
    litellm.failure_callback = []

    get_llm()

    assert "langfuse" in litellm.success_callback
    assert "langfuse" in litellm.failure_callback


def test_langfuse_disabled_when_keys_missing(monkeypatch) -> None:
    """When Langfuse keys are absent, callbacks should remain empty."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    from atlas.config import get_settings
    from atlas.llm.router import get_llm

    get_settings.cache_clear()
    get_llm.cache_clear()

    # Reset callbacks before test
    litellm.success_callback = []
    litellm.failure_callback = []

    get_llm()

    assert "langfuse" not in litellm.success_callback
    assert "langfuse" not in litellm.failure_callback
