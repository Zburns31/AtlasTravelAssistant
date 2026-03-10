"""
Atlas configuration — loads all settings from environment variables / .env file.

Usage:
    from atlas.config import settings

    model = settings.atlas_llm_model
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings resolved from environment variables.

    All fields map 1-to-1 to the variables documented in ``.env.example``.
    Validation is performed by Pydantic on startup; missing required fields
    raise a clear ``ValidationError`` rather than failing silently at runtime.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # LLM (all routing handled by LiteLLM via model string prefix)
    # ------------------------------------------------------------------
    openrouter_api_key: str = Field(
        default="",
        description=(
            "OpenRouter API key. Get one at https://openrouter.ai/keys. "
            "Required when ATLAS_LLM_MODEL starts with 'openrouter/'."
        ),
    )
    groq_api_key: str = Field(
        default="",
        description=(
            "Groq API key. Get one at https://console.groq.com. "
            "Required when ATLAS_LLM_MODEL starts with 'groq/'."
        ),
    )
    google_api_key: str = Field(
        default="",
        description=(
            "Google AI API key (for Gemini via LiteLLM). "
            "Required when ATLAS_LLM_MODEL starts with 'gemini/'."
        ),
    )
    atlas_llm_model: str = Field(
        default="openai/gpt-4o",
        description=(
            "LiteLLM model string.  The prefix selects the provider: "
            "openrouter/<model>, groq/<model>, gemini/<model>, "
            "openai/<model>, anthropic/<model>, etc."
        ),
    )
    atlas_llm_temperature: float = Field(
        default=0.7,
        description="Default sampling temperature for the LLM.",
    )
    atlas_llm_num_retries: int = Field(
        default=3,
        description=(
            "Number of retries on transient LLM errors (429, 500). "
            "Uses exponential backoff between retries."
        ),
    )
    atlas_llm_request_timeout: float = Field(
        default=30.0,
        description="Per-request timeout in seconds for LLM calls.",
    )
    atlas_llm_call_delay: float = Field(
        default=3.0,
        description=(
            "Minimum delay in seconds between consecutive LLM calls. "
            "Helps stay within free-tier RPM quotas (~20 RPM). "
            "Set to 0.0 to disable throttling."
        ),
    )
    atlas_llm_max_tokens: int | None = Field(
        default=1024,
        description=(
            "Default max_tokens for LLM responses. Applied to planning "
            "phases (ingest, enrich, decompose). Set to None for no limit."
        ),
    )

    # ------------------------------------------------------------------
    # Langfuse observability (optional)
    # ------------------------------------------------------------------
    langfuse_public_key: str = Field(
        default="",
        description="Langfuse public key. When set (with secret key), enables LLM tracing.",
    )
    langfuse_secret_key: str = Field(
        default="",
        description="Langfuse secret key. Required together with public key.",
    )
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse API host. Override for self-hosted instances.",
    )

    # ------------------------------------------------------------------
    # External services
    # ------------------------------------------------------------------
    serper_api_key: str = Field(
        default="",
        description=(
            "Serper.dev API key for Google Search / Places. "
            "Get a free key at https://serper.dev (2 500 queries free)."
        ),
    )

    # ------------------------------------------------------------------
    # Auto-fetch (enrich search results with page content)
    # ------------------------------------------------------------------
    atlas_fetch_top_n: int = Field(
        default=1,
        description=(
            "Number of top search_web results to auto-fetch and extract "
            "page content for. Set to 0 to disable auto-fetching."
        ),
    )
    atlas_fetch_max_chars: int = Field(
        default=1500,
        description="Max characters of extracted page content per URL.",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    atlas_debug: bool = Field(
        default=False,
        description="Enable debug mode (verbose logging, Dash debug server).",
    )
    atlas_host: str = Field(
        default="127.0.0.1",
        description="Host for the Dash development server.",
    )
    atlas_port: int = Field(
        default=8050,
        description="Port for the Dash development server.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application ``Settings`` instance.

    The result is cached after the first call so ``.env`` is read only once
    per process.  Call ``get_settings.cache_clear()`` in tests to reload.
    """
    return Settings()


#: Module-level convenience alias — ``from atlas.config import settings``.
settings: Settings = get_settings()
