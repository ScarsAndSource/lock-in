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

    # --- Redis (shared limits, locks, idempotency, kill-switch, breaker) -----
    # Empty REDIS_URL => everything falls back to the in-process behaviour (one instance = exact).
    # Redis is treated as a volatile cache: nothing here may be the only copy of something that matters.
    redis_url: str = ""  # redis://... or rediss://... (TLS)
    redis_socket_timeout_seconds: float = Field(default=0.15, gt=0, le=2)    # a slow Redis must never slow the app
    redis_connect_timeout_seconds: float = Field(default=0.5, gt=0, le=5)
    redis_max_connections: int = Field(default=20, ge=1)

    # One chat turn in flight per user. Must outlast the slowest legitimate turn (planner + answer + a retry).
    chat_inflight_lock_seconds: int = Field(default=40, ge=0, le=300)  # 0 = lock off
    idempotency_ttl_seconds: int = Field(default=120, ge=10, le=3600)  # how long a finished reply can be replayed

    # Circuit breaker on the AI provider: N failures inside the window opens it for the cooldown.
    ai_breaker_failures: int = Field(default=5, ge=1)
    ai_breaker_window_seconds: int = Field(default=30, ge=1)
    ai_breaker_cooldown_seconds: int = Field(default=20, ge=1)

    # --- database pool (batch 4) -------------------------------------------------
    # A request holds its DB connection while the model answers, so the pool is the real concurrency ceiling. Waiting
    # for a free connection longer than db_pool_timeout_seconds fails fast with a 503 instead of queueing forever.
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    db_pool_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    # Model calls in flight per instance. Beyond it a call waits up to ai_slot_wait_seconds, then takes the same
    # deterministic fallback as an outage (nothing is charged). 0 = no limit.
    ai_max_concurrent: int = Field(default=6, ge=0, le=100)
    ai_slot_wait_seconds: float = Field(default=3.0, ge=0, le=30)

    # --- client IP behind a proxy (batch 4) ----------------------------------------
    # How many proxies in front of the app APPEND to X-Forwarded-For (Render's load balancer = 1; Cloudflare in front
    # of Render = 2). The Nth entry from the RIGHT is the client: everything to its left is client-controlled.
    # 0 = ignore the header and use the socket peer.
    trusted_proxy_hops: int = Field(default=1, ge=0, le=5)

    # --- global AI ceiling (batch 4) -----------------------------------------------
    # Provider calls / tokens across ALL users per UTC day. When either reaches ai_global_trip_fraction of its cap the
    # global AI-off flag is set until 00:00 UTC (Sentry alert + audit event). 0 = that ceiling is off.
    ai_global_daily_calls: int = Field(default=0, ge=0)
    ai_global_daily_tokens: int = Field(default=0, ge=0)
    ai_global_trip_fraction: float = Field(default=0.9, gt=0, le=1)

    # --- abuse strikes (batch 4) ---------------------------------------------------
    # Each detection adds weighted strikes that expire after strike_window_seconds. At the soft threshold the person's
    # AI rate limits halve for strike_halve_seconds; at the hard threshold AI is switched off for them (first time
    # strike_ban_first_seconds, after that strike_ban_repeat_seconds) and from strike_review_offenses offenses it is
    # also flagged for review. AI only: the tracker, undo and the crisis path are never affected.
    strike_window_seconds: int = Field(default=86_400, ge=60)
    strike_soft_threshold: int = Field(default=4, ge=1)
    strike_hard_threshold: int = Field(default=8, ge=2)
    strike_halve_seconds: int = Field(default=3_600, ge=60)
    strike_ban_first_seconds: int = Field(default=3_600, ge=60)
    strike_ban_repeat_seconds: int = Field(default=86_400, ge=60)
    strike_offense_memory_seconds: int = Field(default=604_800, ge=3600)
    strike_review_offenses: int = Field(default=3, ge=1)
    strike_storm_threshold: int = Field(default=10, ge=0)    # this many 429s inside the window = one strike; 0 = off
    strike_storm_window_seconds: int = Field(default=60, ge=1)

    # --- security audit trail (batch 4) ----------------------------------------------
    ai_event_retention_days: int = Field(default=30, ge=1)    # python -m app.jobs.prune_ai_security_events

    # --- production boot guard (batch 4) -------------------------------------------
    # With APP_ENV=production the app refuses to start on an unsafe setup. Set this only to run a single instance
    # without Redis on purpose (limits then live in one process and reset on every restart).
    allow_no_redis: bool = False

    # --- caching, weighted AI budget, audio limits ----------------------------
    facts_cache_ttl_seconds: int = Field(default=60, ge=0, le=900)      # 0 = off. Data-version invalidation does the real work; this is the safety net
    answer_cache_ttl_seconds: int = Field(default=600, ge=0, le=3600)   # 0 = off
    media_cache_ttl_seconds: int = Field(default=600, ge=0, le=3600)    # 0 = off
    llm_daily_unit_cap: int = Field(default=120, ge=0)                  # weighted calls per user per UTC day (text 1, audio 2, vision 3); 0 = off
    llm_daily_token_cap: int = Field(default=200_000, ge=0)             # provider tokens per user per UTC day; 0 = off
    max_audio_seconds: int = Field(default=75, ge=5, le=600)

    # --- LLM (Groq) -------------------------------------------------------
    groq_api_key: str = ""  # empty => every narration falls back to deterministic text
    groq_model: str = "llama-3.3-70b-versatile"  # check Groq's current model list before deploy
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = Field(default=10.0, gt=0, le=60)  # a request holds its DB connection while Groq answers: keep this short
    groq_max_retries: int = Field(default=0, ge=0, le=2)  # transport-level retries per Groq call; 0 = one attempt, fall back fast
    groq_transcribe_model: str = "whisper-large-v3-turbo"  # voice check-in; check Groq's current model list
    groq_vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"  # screenshot screen time; same advice
    max_audio_bytes: int = Field(default=4_000_000, ge=10_000)
    max_image_bytes: int = Field(default=2_800_000, ge=10_000)  # NOT read anywhere yet: the enforced cap is screenshot_parser.MAX_IMAGE_BYTES
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

    @model_validator(mode="after")
    def _check_strikes(self) -> "Settings":
        if self.strike_hard_threshold <= self.strike_soft_threshold:
            raise ValueError("STRIKE_HARD_THRESHOLD must be higher than STRIKE_SOFT_THRESHOLD.")
        return self

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.app_env.strip().lower() not in {"production", "prod"}:
            return self
        problems: list[str] = []
        if not self.rate_limit_enabled:
            problems.append("RATE_LIMIT_ENABLED must be true")
        if any("localhost" in o or "127.0.0.1" in o for o in self.cors_allow_origins):
            problems.append("CORS_ALLOW_ORIGINS must not contain localhost or 127.0.0.1")
        if not self.redis_url and not self.allow_no_redis:
            problems.append("REDIS_URL is required (or ALLOW_NO_REDIS=true to run one instance without shared limits)")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems) + ".")
        return self

    @property
    def old_encryption_keys(self) -> list[str]:
        return [k.strip() for k in self.field_encryption_old_keys.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
