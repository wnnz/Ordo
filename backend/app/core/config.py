from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "development-only-secret-change-me"
    credential_encryption_key: str | None = None
    database_url: str = "sqlite+aiosqlite:///./ordo.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_path: str = "./data/files"
    access_token_minutes: int = 720
    cors_origins: str = "http://localhost:5173"
    sandbox_url: str = "http://localhost:8081"
    sandbox_shared_secret: str = ""
    sandbox_artifact_path: str = "./data/sandbox-artifacts"
    host_info_agent_url: str = "http://host.docker.internal:8765"
    host_info_agent_token: str = ""
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    max_request_body_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    public_rate_limit_requests: int = Field(default=30, ge=0, le=100_000)
    public_access_rate_limit_requests: int = Field(default=10, ge=0, le=100_000)
    public_upload_rate_limit_requests: int = Field(default=10, ge=0, le=100_000)
    public_rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    public_max_active_runs_per_app: int = Field(default=10, ge=1, le=10_000)
    workflow_run_lease_seconds: int = Field(default=120, ge=30, le=86_400)
    workflow_pending_recovery_seconds: int = Field(default=60, ge=30, le=86_400)
    file_upload_retention_hours: int = Field(default=24, ge=1, le=8760)
    file_output_retention_days: int = Field(default=30, ge=1, le=3650)
    file_orphan_grace_hours: int = Field(default=24, ge=1, le=8760)
    file_cleanup_batch_size: int = Field(default=500, ge=1, le=10_000)
    disable_user_registration: bool = False
    log_level: str = "INFO"
    otel_exporter_otlp_endpoint: str = ""
    alert_webhook_url: str = ""
    task_always_eager: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
