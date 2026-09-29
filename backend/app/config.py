"""
Centralized app configuration. Everything secret or environment-specific
comes from env vars — nothing here is a real credential, and nothing here
should ever be hardcoded elsewhere in the app.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development")

    # Postgres connection string (Supabase project's DB, asyncpg driver).
    # Example: postgresql+asyncpg://user:pass@host:5432/postgres
    database_url: str = Field(...)

    # Supabase issues JWTs signed with this shared secret (HS256) for
    # projects on the legacy JWT signing scheme. ASSUMPTION FLAGGED: if this
    # Supabase project instead uses the newer asymmetric (RS256/ES256) JWT
    # signing keys, verify_supabase_jwt in security.py must be switched to
    # fetch and cache the project's JWKS instead of using this shared
    # secret directly. This was not verified against a live project because
    # no Supabase project credentials exist yet — check the project's
    # Auth settings before deploying past local dev.
    supabase_jwt_secret: str = Field(...)
    supabase_jwt_audience: str = Field(default="authenticated")

    # Fernet key for field-level encryption of urge/journal text. Generate
    # with `cryptography.fernet.Fernet.generate_key()` — must be 32
    # url-safe base64-encoded bytes. Rotating this key without a migration
    # plan makes existing encrypted rows undecryptable, so treat it like
    # any other credential that must never be lost, not just never leaked.
    field_encryption_key: str = Field(...)

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
