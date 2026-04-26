from pydantic_settings import BaseSettings
from pydantic import validator
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://shamba:shamba@localhost:5432/shamba"
    redis_url: str = "redis://localhost:6379"
    anthropic_api_key: str = ""
    kamis_base_url: str = "https://kamis.kilimo.go.ke"
    environment: str = "development"

    @validator("database_url", pre=True)
    def fix_db_url(cls, v):
        return v.replace("postgresql://", "postgresql+asyncpg://")

    # Scraper settings
    scraper_entries_per_page: int = 3000
    scraper_request_delay_seconds: float = 0.3
    scraper_request_timeout: int = 30

    # Cache TTLs (seconds)
    cache_ttl_daily: int = 3600        # 1 hour
    cache_ttl_trend: int = 21600       # 6 hours
    cache_ttl_compare: int = 7200      # 2 hours
    cache_ttl_summary: int = 1800      # 30 minutes
    cache_ttl_static: int = 86400      # 24 hours

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
