from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from TC_* and explicit provider variables."""

    model_config = SettingsConfigDict(
        env_prefix="TC_",
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )

    service_name: str = "triathlon-coach"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    frontend_origins: str | None = Field(default=None, validation_alias="FRONTEND_ORIGINS")
    frontend_origin: str = Field(
        default="http://127.0.0.1:5173",
        validation_alias="FRONTEND_ORIGIN",
    )
    database_url: str = Field(
        default=(
            "postgresql+psycopg://triathlon:triathlon@localhost:5432/"
            "triathlon_coach"
        ),
        validation_alias=AliasChoices("TC_DATABASE_URL", "sqlalchemy.url"),
    )

    auth_mode: Literal["development", "session"] = "development"
    session_cookie_name: str = Field(
        default="tricoach_session", min_length=1, max_length=128
    )
    session_ttl_seconds: int = Field(default=14 * 24 * 60 * 60, ge=60)
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_path: str = "/"
    csrf_cookie_name: str = Field(
        default="tricoach_csrf", min_length=1, max_length=128
    )
    csrf_header_name: str = Field(
        default="X-CSRF-Token", min_length=1, max_length=128
    )

    login_rate_limit_failures: int = Field(default=5, ge=1, le=100)
    login_rate_limit_window_seconds: int = Field(default=15 * 60, ge=1, le=86400)
    login_rate_limit_max_keys: int = Field(default=10000, ge=100, le=1000000)
    max_active_sessions_per_user: int = Field(default=10, ge=1, le=1000)
    revoked_session_retention_days: int = Field(default=30, ge=0, le=3650)
    strava_client_id: str | None = Field(
        default=None, validation_alias="STRAVA_CLIENT_ID"
    )
    strava_client_secret: SecretStr | None = Field(
        default=None, validation_alias="STRAVA_CLIENT_SECRET"
    )
    strava_redirect_uri: str | None = Field(
        default=None, validation_alias="STRAVA_REDIRECT_URI"
    )
    strava_authorization_url: str = Field(
        default="https://www.strava.com/oauth/authorize",
        validation_alias="STRAVA_AUTHORIZATION_URL",
    )
    strava_token_url: str = Field(
        default="https://www.strava.com/oauth/token",
        validation_alias="STRAVA_TOKEN_URL",
    )
    strava_revocation_url: str = Field(
        default="https://www.strava.com/oauth/revoke",
        validation_alias="STRAVA_REVOCATION_URL",
    )
    strava_api_base_url: str = Field(
        default="https://www.strava.com/api/v3",
        validation_alias="STRAVA_API_BASE_URL",
    )
    strava_scopes: str | None = Field(
        default=None, validation_alias="STRAVA_SCOPES"
    )
    oauth_state_ttl_seconds: int = Field(
        default=600, validation_alias="OAUTH_STATE_TTL_SECONDS"
    )
    oauth_state_sqlite_path: str | None = Field(
        default=None, validation_alias="OAUTH_STATE_SQLITE_PATH"
    )
    oauth_state_diagnostics: bool = Field(
        default=False, validation_alias="OAUTH_STATE_DIAGNOSTICS"
    )
    strava_import_page_size: int = Field(
        default=100, validation_alias="STRAVA_IMPORT_PAGE_SIZE"
    )
    strava_import_retry_seconds: int = Field(
        default=60, validation_alias="STRAVA_IMPORT_RETRY_SECONDS"
    )
    strava_import_overlap_seconds: int = Field(
        default=86400, validation_alias="STRAVA_IMPORT_OVERLAP_SECONDS"
    )

    activity_stream_retention_enabled: bool = True
    activity_location_stream_retention_enabled: bool = False
    activity_stream_max_samples: int = Field(default=1000, ge=2, le=10000)
    activity_stream_retention_days: int = Field(default=0, ge=0, le=3650)
    @field_validator("frontend_origin")
    @classmethod
    def validate_frontend_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            value == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("FRONTEND_ORIGIN must be one explicit HTTP origin")
        return value.rstrip("/")


    def allowed_frontend_origins(self) -> tuple[str, ...]:
        configured = self.frontend_origins or (self.frontend_origin + ",http://localhost:5173")
        return tuple(dict.fromkeys(value.strip().rstrip("/") for value in configured.split(",") if value.strip()))

    @model_validator(mode="after")
    def validate_auth_security(self):
        if self.environment.casefold() in {"production", "prod"} and self.auth_mode == "session" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true for session authentication in production")
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None requires SESSION_COOKIE_SECURE=true")
        if self.session_cookie_name == self.csrf_cookie_name:
            raise ValueError("Session and CSRF cookie names must differ")
        return self
    @field_validator("frontend_origins")
    @classmethod
    def validate_frontend_origins(cls, value: str | None) -> str | None:
        if value is None:
            return None
        origins = [item.strip() for item in value.split(",") if item.strip()]
        if not origins:
            raise ValueError("FRONTEND_ORIGINS must contain explicit HTTP origins")
        for origin in origins:
            cls.validate_frontend_origin(origin)
        return ",".join(origins)
    @field_validator("session_cookie_path")
    @classmethod
    def validate_session_cookie_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("SESSION_COOKIE_PATH must start with /")
        return value

    @field_validator("session_cookie_name", "csrf_cookie_name", "csrf_header_name")
    @classmethod
    def validate_http_name(cls, value: str) -> str:
        if value.strip() != value or any(character.isspace() for character in value):
            raise ValueError("Cookie and header names cannot contain whitespace")
        return value

@lru_cache
def get_settings() -> Settings:
    return Settings()
