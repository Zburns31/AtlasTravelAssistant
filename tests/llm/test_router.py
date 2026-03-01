"""Tests for the LLM router (``atlas.llm.router``)."""

from __future__ import annotations


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
    assert llm.model_name == "anthropic/claude-3-5-sonnet"


def test_get_llm_is_cached() -> None:
    """Successive calls should return the *same* cached instance."""
    from atlas.llm.router import get_llm

    get_llm.cache_clear()

    a = get_llm()
    b = get_llm()
    assert a is b
