"""Centralized configuration. Secrets come from env vars only."""
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = Field(...)

    # --- auth -------------------------------------------------------------
    auth_mode: Literal["hs256", "jwks"] = "hs256"
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_issuer: str = ""

    # --- encryption -------------------------------------------------------
    field_encryption_key: str = Field(...)
    field_encryption_old_keys: str = ""  # comma separated, for rotation

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- safety rails -----------------------------------------------------
    rls_enforced: bool = True
    schema_check_mode: Literal["off", "warn", "strict"] = "warn"

    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = Field(default=120, ge=1)
    rate_limit_export_per_hour: int = Field(default=5, ge=1)
    rate_limit_insights_refresh_per_hour: int = Field(default=10, ge=1)

    # --- LLM (Groq) -------------------------------------------------------
    groq_api_key: str = ""  # empty => every narration falls back to deterministic text
    groq_model: str = "llama-3.3-70b-versatile"  # check Groq's current model list before deploy
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
    llm_daily_call_cap: int = Field(default=80, ge=1)  # per user per UTC day, all features, retries included
    rate_limit_chat_per_minute: int = Field(default=6, ge=1)
    rate_limit_chat_per_hour: int = Field(default=60, ge=1)
    chat_retention_days: int = Field(default=90, ge=0)  # stored threads idle this long are pruned; 0 = keep forever

    # --- tasks, reminders, web push -------------------------------------------
    rate_limit_capture_per_minute: int = Field(default=10, ge=1)
    rate_limit_push_test_per_hour: int = Field(default=6, ge=1)
    vapid_public_key: str = ""   # empty => push is off; the in-app task list still works
    vapid_private_key: str = ""
    vapid_subject: str = ""      # "mailto:you@example.com" -- push services use it to contact you if needed
    # A subscription endpoint is a URL OUR SERVER will POST to, so it must be a real push service (SSRF guard).
    push_allowed_host_suffixes: list[str] = Field(
        default_factory=lambda: [
            "fcm.googleapis.com", "push.services.mozilla.com", "push.apple.com", "notify.windows.com",
        ]
    )



    @model_validator(mode="after")
    def _check_auth_config(self) -> "Settings":
        if self.auth_mode == "hs256" and not self.supabase_jwt_secret:
            raise ValueError("AUTH_MODE=hs256 requires SUPABASE_JWT_SECRET.")
        if self.auth_mode == "jwks" and not self.supabase_jwks_url:
            raise ValueError("AUTH_MODE=jwks requires SUPABASE_JWKS_URL.")
        return self

    @property
    def old_encryption_keys(self) -> list[str]:
        return [k.strip() for k in self.field_encryption_old_keys.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
