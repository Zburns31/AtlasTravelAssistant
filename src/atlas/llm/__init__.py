"""LLM router — single entry point for all model access.

Usage:
    from atlas.llm import get_llm, throttle_llm_call

    llm = get_llm()  # returns BaseChatModel via OpenRouter
    throttle_llm_call()  # enforce inter-call delay
    llm.invoke(messages)
"""

from atlas.llm.router import get_llm, throttle_llm_call

__all__ = ["get_llm", "throttle_llm_call"]
