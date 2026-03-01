"""LLM router — single entry point for all model access.

Usage:
    from atlas.llm import get_llm

    llm = get_llm()  # returns BaseChatModel backed by OpenRouter
"""

from atlas.llm.router import get_llm

__all__ = ["get_llm"]
