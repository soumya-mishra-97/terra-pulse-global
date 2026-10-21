"""Application configuration loaded from environment variables (see ../.env.example).

Secrets (the Anthropic API key, database password) are read from the environment only and
are never serialised into API responses or logs.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'var' / 'terrapulse.db'}"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- LLM (optional). No key => deterministic demo mode. ---
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_max_output_tokens: int = Field(default=1500, ge=128, le=16000)
    llm_report_max_output_tokens: int = Field(default=4000, ge=256, le=16000)
    # Server-side refusal fallbacks (beta). Disable if your account/proxy rejects the beta header.
    llm_server_fallbacks: bool = True

    # --- Data freshness ---
    stale_after_days: int = Field(default=730, description="Reference date older than this => stale")
    snapshot_dir: Path = BACKEND_DIR / "data" / "snapshots"
    methodology_dir: Path = BACKEND_DIR / "data" / "methodology"

    # --- Reports ---
    storage_backend: Literal["local", "s3"] = "local"
    storage_dir: Path = BACKEND_DIR / "var" / "reports"
    s3_bucket: str | None = None
    s3_prefix: str = "terrapulse/reports/"
    report_execution: Literal["thread", "inline"] = "thread"
    report_workers: int = Field(default=2, ge=1, le=8)
    report_max_attempts: int = Field(default=2, ge=1, le=3)
    report_timeout_seconds: float = 180.0
    max_active_reports_per_user: int = 2
    idempotency_window_seconds: int = 600

    # --- Auth & rate limits (demo identity; replace with OIDC in production) ---
    auth_mode: Literal["demo"] = "demo"
    copilot_requests_per_minute: int = 20
    report_requests_per_hour: int = 20

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
