from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Async PDF Toolkit API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    api_key: str | None = Field(default=None, alias="API_KEY")

    max_upload_bytes: int = Field(default=20_000_000, alias="MAX_UPLOAD_BYTES", ge=1)
    max_pdf_pages: int = Field(default=100, alias="MAX_PDF_PAGES", ge=1)
    max_concurrent_jobs: int = Field(default=2, alias="MAX_CONCURRENT_JOBS", ge=1)
    rate_limit_per_minute: int = Field(default=30, alias="RATE_LIMIT_PER_MINUTE", ge=1)
    job_timeout_seconds: float = Field(default=300.0, alias="JOB_TIMEOUT_SECONDS", gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
