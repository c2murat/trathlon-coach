from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from TC_* and explicit provider variables."""

    model_config = SettingsConfigDict(
        env_prefix="TC_",
        case_sensitive=False,
        populate_by_name=True,
    )

    service_name: str = "triathlon-coach"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    database_url: str = (
        "postgresql+psycopg://triathlon:triathlon@localhost:5432/triathlon_coach"
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
    strava_scopes: str | None = Field(
        default=None, validation_alias="STRAVA_SCOPES"
    )
    oauth_state_ttl_seconds: int = Field(
        default=600, validation_alias="OAUTH_STATE_TTL_SECONDS"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
