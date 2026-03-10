"""Tests for the LLM router (``atlas.llm.router``)."""

from __future__ import annotations

import time

from langchain_core.language_models import BaseChatModel


# ── Core behaviour ──────────────────────────────────────────────────


def test_get_llm_returns_base_chat_model() -> None:
    """``get_llm()`` should return a ``BaseChatModel``."""
    from atlas.llm.router import get_llm

    get_llm.cache_clear()

    llm = get_llm()
    assert isinstance(llm, BaseChatModel)


def test_get_llm_returns_chat_litellm() -> None:
    """``get_llm()`` should return a ``ChatLiteLLM`` instance."""
    from langchain_litellm import ChatLiteLLM

    from atlas.llm.router import get_llm

    get_llm.cache_clear()

    llm = get_llm()
    assert isinstance(llm, ChatLiteLLM)


def test_get_llm_is_cached() -> None:
    """Successive calls should return the *same* cached instance."""
    from atlas.llm.router import get_llm

    get_llm.cache_clear()

    a = get_llm()
    b = get_llm()
    assert a is b


def test_get_llm_uses_configured_model(monkeypatch) -> None:
    """``get_llm()`` should respect ``ATLAS_LLM_MODEL``."""
    monkeypatch.setenv("ATLAS_LLM_MODEL", "groq/llama-3.3-70b-versatile")

    from atlas.config import get_settings
    from atlas.llm.router import get_llm

    get_settings.cache_clear()
    get_llm.cache_clear()

    llm = get_llm()
    assert llm.model == "groq/llama-3.3-70b-versatile"


def test_get_llm_uses_configured_temperature(monkeypatch) -> None:
    """``get_llm()`` should respect ``ATLAS_LLM_TEMPERATURE``."""
    monkeypatch.setenv("ATLAS_LLM_TEMPERATURE", "0.2")

    from atlas.config import get_settings
    from atlas.llm.router import get_llm

    get_settings.cache_clear()
    get_llm.cache_clear()

    llm = get_llm()
    assert llm.temperature == 0.2


# ── Langfuse callback tests ────────────────────────────────────────


def test_langfuse_enabled_when_keys_present(monkeypatch) -> None:
    """When both Langfuse keys are set, the LLM should have a Langfuse callback."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    from atlas.config import get_settings
    from atlas.llm.router import get_llm

    get_settings.cache_clear()
    get_llm.cache_clear()

    llm = get_llm()

    callback_types = [type(cb).__name__ for cb in (llm.callbacks or [])]
    assert "LangchainCallbackHandler" in callback_types


def test_langfuse_disabled_when_keys_missing(monkeypatch) -> None:
    """When Langfuse keys are absent, no Langfuse callback should be present."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    from atlas.config import get_settings
    from atlas.llm.router import get_llm

    get_settings.cache_clear()
    get_llm.cache_clear()

    llm = get_llm()

    callbacks = llm.callbacks or []
    callback_types = [type(cb).__name__ for cb in callbacks]
    assert "LangchainCallbackHandler" not in callback_types


# ── Throttle tests ──────────────────────────────────────────────────


def test_throttle_enforces_delay(monkeypatch) -> None:
    """``throttle_llm_call`` should sleep when calls are too close together."""
    monkeypatch.setenv("ATLAS_LLM_CALL_DELAY", "0.1")

    from atlas.config import get_settings
    from atlas.llm.router import throttle_llm_call
    import atlas.llm.router as router_mod

    get_settings.cache_clear()

    # Reset the last-call timestamp
    router_mod._last_call_ts = 0.0

    # First call — no delay expected
    throttle_llm_call()
    t1 = time.monotonic()

    # Second call immediately after — should sleep ~0.1s
    throttle_llm_call()
    t2 = time.monotonic()

    # The gap should be at least the configured delay
    assert (t2 - t1) >= 0.09  # allow slight float tolerance


def test_throttle_disabled_when_zero(monkeypatch) -> None:
    """Setting delay to 0 should skip sleeping."""
    monkeypatch.setenv("ATLAS_LLM_CALL_DELAY", "0")

    from atlas.config import get_settings
    from atlas.llm.router import throttle_llm_call
    import atlas.llm.router as router_mod

    get_settings.cache_clear()
    router_mod._last_call_ts = 0.0

    t1 = time.monotonic()
    throttle_llm_call()
    throttle_llm_call()
    t2 = time.monotonic()

    # Both calls should complete almost instantly (< 50ms)
    assert (t2 - t1) < 0.05
