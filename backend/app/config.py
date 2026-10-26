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
    groq_timeout_seconds: float = Field(default=10.0, gt=0, le=60)  # a request holds its DB connection while Groq answers: keep this short
    groq_max_retries: int = Field(default=0, ge=0, le=2)  # transport-level retries per Groq call; 0 = one attempt, fall back fast
    groq_transcribe_model: str = "whisper-large-v3-turbo"  # voice check-in; check Groq's current model list
    groq_vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"  # screenshot screen time; same advice
    max_audio_bytes: int = Field(default=4_000_000, ge=10_000)
    max_image_bytes: int = Field(default=4_000_000, ge=10_000)
    rate_limit_media_per_minute: int = Field(default=6, ge=1)   # voice + screenshot uploads, per user
    rate_limit_media_per_hour: int = Field(default=40, ge=1)
    llm_daily_call_cap: int = Field(default=80, ge=1)  # per user per UTC day, all features, retries included
    rate_limit_chat_per_minute: int = Field(default=6, ge=1)
    rate_limit_chat_per_hour: int = Field(default=60, ge=1)
    chat_retention_days: int = Field(default=90, ge=0)  # stored threads idle this long are pruned; 0 = keep forever

    # --- error reporting -----------------------------------------------------
    sentry_dsn: str = ""              # empty => error reporting is off
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0, le=1)  # performance tracing; 0 = errors only
    release: str = ""                 # shown on events; falls back to RENDER_GIT_COMMIT

    # --- tasks, reminders, web push -------------------------------------------
    rate_limit_capture_per_minute: int = Field(default=10, ge=1)
    rate_limit_push_test_per_hour: int = Field(default=6, ge=1)
    vapid_public_key: str = ""   # empty => push is off; the in-app task list still works
    vapid_private_key: str = ""
    vapid_subject: str = ""      # "mailto:you@example.com" -- push services use it to contact you if needed
    # Actionable pushes: the service worker POSTs a signed, single-use, short-lived token back to the API.
    # Empty secret => derived from FIELD_ENCRYPTION_KEY (stable across restarts; rotate by setting this explicitly).
    push_action_secret: str = ""
    public_api_url: str = ""      # origin the service worker should POST actions to; empty => same origin as the app
    rate_limit_ingest_per_minute: int = Field(default=20, ge=1)        # per ingest token
    rate_limit_crew_lookup_per_hour: int = Field(default=30, ge=1)   # username claim / invite / block lookups, per user
    rate_limit_crew_code_per_hour: int = Field(default=10, ge=1)     # invite-code join attempts, per user
    rate_limit_push_action_per_minute: int = Field(default=30, ge=1)   # per client IP: the action endpoint has no session
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
