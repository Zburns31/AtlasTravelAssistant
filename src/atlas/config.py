"""
Atlas configuration — loads all settings from environment variables / .env file.

Usage:
    from atlas.config import settings

    api_key = settings.openrouter_api_key
    model   = settings.atlas_llm_model
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
    # LLM / OpenRouter
    # ------------------------------------------------------------------
    openrouter_api_key: str = Field(
        ...,
        description="API key for OpenRouter (https://openrouter.ai/keys).",
    )
    atlas_llm_model: str = Field(
        default="openai/gpt-4o",
        description=(
            "OpenRouter model string used by get_llm(). "
            "Examples: openai/gpt-4o, anthropic/claude-3-5-sonnet, "
            "google/gemini-2.0-flash"
        ),
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL for the OpenRouter OpenAI-compatible API.",
    )

    # ------------------------------------------------------------------
    # External services
    # ------------------------------------------------------------------
    atlas_weather_api_key: str = Field(
        default="",
        description="API key for the weather service used by the weather tool.",
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
