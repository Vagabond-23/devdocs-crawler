"""
Application configuration via pydantic-settings.

All settings are loaded from environment variables (or .env file).
Grouped by concern for maintainability.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the DevDocs Crawler application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://devdocs:devdocs_secret@localhost:5432/devdocs"

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Meilisearch ───────────────────────────────────────────
    meili_url: str = "http://localhost:7700"
    meili_master_key: str = "devdocs_meili_master_key"

    # ── Crawler ───────────────────────────────────────────────
    crawler_max_workers: int = 8
    crawler_max_depth: int = 3
    crawler_max_pages_per_host: int = 5000
    crawler_default_delay_ms: int = 1000
    crawler_request_timeout: int = 30
    crawler_max_retries: int = 3
    crawler_user_agent: str = "DevDocsCrawler/1.0 (+https://github.com/devdocs-crawler)"
    crawler_allowed_hosts: str = (
        "docs.python.org,developer.mozilla.org,fastapi.tiangolo.com,kubernetes.io"
    )

    # ── API ───────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def allowed_hosts_list(self) -> list[str]:
        """Parse comma-separated allowed hosts into a list."""
        return [h.strip() for h in self.crawler_allowed_hosts.split(",") if h.strip()]


# Singleton instance — import this across the application.
settings = Settings()
