"""LLM router — single entry point for all model access.

Usage:
    from atlas.llm import get_llm

    llm = get_llm()  # returns BaseChatModel backed by LiteLLM
"""

from atlas.llm.router import get_llm

__all__ = ["get_llm"]
