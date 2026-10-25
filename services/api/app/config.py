from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTSCOPE_", extra="ignore")

    database_url: str = "sqlite:///./agentscope.db"
    cors_origins: str = "http://localhost:3070"
    max_event_bytes: int = 262_144
    retention_days: int = 90

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
