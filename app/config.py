"""app.config — single source of truth for runtime configuration.

All tunable values are read here via pydantic-settings. No other module
reads environment variables directly; they import ``settings`` instead.

Design notes
------------
- The .env file is optional (pydantic-settings falls back to defaults). This
  lets the routing engine run out-of-the-box without any local config.
- Routing thresholds are exposed as fields so tests can construct a custom
  ``Settings`` instance and exercise different tier boundaries.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / ``.env`` file.

    Attributes:
        All attributes have safe defaults so a fresh clone works with zero
        configuration. Override via environment variables or ``.env``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM provider keys (not used by Stage 1 routing; present for later stages) ---
    openai_api_key: str = ""
    local_llm_api_base: str = "http://localhost:11434/v1"

    # --- Model tier mapping ---
    router_model_complex: str = "gpt-4o"
    router_model_chat: str = "gpt-4o-mini"
    router_model_parse: str = "llama3:8b"

    # --- Routing score thresholds (0-100) ---
    # WHY: score<=PARSE_MAX -> PARSE; PARSE_MAX<score<=CHAT_MAX -> CHAT; else COMPLEX.
    routing_parse_max: int = Field(default=35, ge=0, le=100)
    routing_chat_max: int = Field(default=55, ge=0, le=100)

    # --- Storage paths (used from Stage 2 onward) ---
    redis_url: str = "redis://localhost:6379/0"
    chroma_persist_dir: str = "./data/chroma"
    wiki_dir: str = "./wiki"

    # --- New v2 file paths (NEW-1 / NEW-2 / NEW-3) ---
    progress_file: str = "PROGRESS.yaml"
    tasks_file: str = "TASKS.jsonl"
    context_dir: str = "./data/context"

    # --- Optional feature flags ---
    enable_streaming: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached ``Settings`` instance.

    Cached so repeated imports are cheap and config is read once at startup.
    Tests that need different values call ``get_settings.cache_clear()``.
    """
    return Settings()


# Module-level singleton: import ``settings`` everywhere instead of reading env.
settings = get_settings()
