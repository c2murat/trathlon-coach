from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
