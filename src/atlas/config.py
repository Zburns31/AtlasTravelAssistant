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
    # LLM / LiteLLM
    # ------------------------------------------------------------------
    atlas_llm_model: str = Field(
        default="openai/gpt-4o",
        description=(
            "LiteLLM model string used by get_llm(). "
            "Format: <provider>/<model>.  Examples: openai/gpt-4o, "
            "anthropic/claude-3-5-sonnet, groq/llama-3.3-70b-versatile, "
            "gemini/gemini-2.0-flash"
        ),
    )
    atlas_llm_temperature: float = Field(
        default=0.7,
        description="Default sampling temperature for the LLM.",
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
