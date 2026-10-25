from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPANTRACE_", extra="ignore")

    database_url: str = Field(default="sqlite:///./agentscope.db", validation_alias=AliasChoices("SPANTRACE_DATABASE_URL", "AGENTSCOPE_DATABASE_URL"))
    cors_origins: str = Field(default="http://localhost:3070", validation_alias=AliasChoices("SPANTRACE_CORS_ORIGINS", "AGENTSCOPE_CORS_ORIGINS"))
    max_event_bytes: int = Field(default=262_144, validation_alias=AliasChoices("SPANTRACE_MAX_EVENT_BYTES", "AGENTSCOPE_MAX_EVENT_BYTES"))
    retention_days: int = Field(default=90, validation_alias=AliasChoices("SPANTRACE_RETENTION_DAYS", "AGENTSCOPE_RETENTION_DAYS"))

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
