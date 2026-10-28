from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPANTRACE_", extra="ignore")

    database_url: str = Field(default="sqlite:///./spantrace.db", validation_alias=AliasChoices("SPANTRACE_DATABASE_URL", "AGENTSCOPE_DATABASE_URL"))
    cors_origins: str = Field(default="http://localhost:3070", validation_alias=AliasChoices("SPANTRACE_CORS_ORIGINS", "AGENTSCOPE_CORS_ORIGINS"))
    max_event_bytes: int = Field(default=262_144, validation_alias=AliasChoices("SPANTRACE_MAX_EVENT_BYTES", "AGENTSCOPE_MAX_EVENT_BYTES"))
    retention_days: int = Field(default=90, validation_alias=AliasChoices("SPANTRACE_RETENTION_DAYS", "AGENTSCOPE_RETENTION_DAYS"))
    repository_storage_path: str = Field(default=".spantrace-data", validation_alias=AliasChoices("SPANTRACE_REPOSITORY_STORAGE_PATH", "AGENTSCOPE_REPOSITORY_STORAGE_PATH"))
    repository_max_archive_bytes: int = Field(default=20 * 1024 * 1024, validation_alias=AliasChoices("SPANTRACE_REPOSITORY_MAX_ARCHIVE_BYTES", "AGENTSCOPE_REPOSITORY_MAX_ARCHIVE_BYTES"))
    repository_max_extracted_bytes: int = Field(default=50 * 1024 * 1024, validation_alias=AliasChoices("SPANTRACE_REPOSITORY_MAX_EXTRACTED_BYTES", "AGENTSCOPE_REPOSITORY_MAX_EXTRACTED_BYTES"))
    repository_max_files: int = Field(default=5000, validation_alias=AliasChoices("SPANTRACE_REPOSITORY_MAX_FILES", "AGENTSCOPE_REPOSITORY_MAX_FILES"))
    repository_max_file_bytes: int = Field(default=1 * 1024 * 1024, validation_alias=AliasChoices("SPANTRACE_REPOSITORY_MAX_FILE_BYTES", "AGENTSCOPE_REPOSITORY_MAX_FILE_BYTES"))
    repository_max_depth: int = Field(default=20, validation_alias=AliasChoices("SPANTRACE_REPOSITORY_MAX_DEPTH", "AGENTSCOPE_REPOSITORY_MAX_DEPTH"))
    repository_analysis_max_source_bytes: int = Field(default=12 * 1024 * 1024, validation_alias=AliasChoices("SPANTRACE_REPOSITORY_ANALYSIS_MAX_SOURCE_BYTES", "AGENTSCOPE_REPOSITORY_ANALYSIS_MAX_SOURCE_BYTES"))
    repository_http_timeout_seconds: float = Field(default=20.0, validation_alias=AliasChoices("SPANTRACE_REPOSITORY_HTTP_TIMEOUT_SECONDS", "AGENTSCOPE_REPOSITORY_HTTP_TIMEOUT_SECONDS"))
    execution_worker_image: str = Field(default="spantrace-worker:0.1.0", validation_alias=AliasChoices("SPANTRACE_EXECUTION_WORKER_IMAGE", "AGENTSCOPE_EXECUTION_WORKER_IMAGE"))
    execution_worker_api_url: str = Field(default="http://host.docker.internal:8070", validation_alias=AliasChoices("SPANTRACE_EXECUTION_WORKER_API_URL", "AGENTSCOPE_EXECUTION_WORKER_API_URL"))
    execution_timeout_seconds: int = Field(default=120, ge=5, le=3600, validation_alias=AliasChoices("SPANTRACE_EXECUTION_TIMEOUT_SECONDS", "AGENTSCOPE_EXECUTION_TIMEOUT_SECONDS"))
    execution_memory_mb: int = Field(default=256, ge=64, le=2048, validation_alias=AliasChoices("SPANTRACE_EXECUTION_MEMORY_MB", "AGENTSCOPE_EXECUTION_MEMORY_MB"))
    execution_cpu_limit: float = Field(default=1.0, gt=0, le=4, validation_alias=AliasChoices("SPANTRACE_EXECUTION_CPU_LIMIT", "AGENTSCOPE_EXECUTION_CPU_LIMIT"))
    execution_pids_limit: int = Field(default=64, ge=16, le=512, validation_alias=AliasChoices("SPANTRACE_EXECUTION_PIDS_LIMIT", "AGENTSCOPE_EXECUTION_PIDS_LIMIT"))
    execution_log_bytes: int = Field(default=256 * 1024, ge=16 * 1024, le=2 * 1024 * 1024, validation_alias=AliasChoices("SPANTRACE_EXECUTION_LOG_BYTES", "AGENTSCOPE_EXECUTION_LOG_BYTES"))
    execution_input_bytes: int = Field(default=64 * 1024, ge=1024, le=512 * 1024, validation_alias=AliasChoices("SPANTRACE_EXECUTION_INPUT_BYTES", "AGENTSCOPE_EXECUTION_INPUT_BYTES"))

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
