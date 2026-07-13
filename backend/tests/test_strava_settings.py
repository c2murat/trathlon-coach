from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from app.core.settings import BACKEND_ENV_FILE, Settings, get_settings


def test_strava_settings_load_from_exact_environment_names(monkeypatch) -> None:
    monkeypatch.setenv("STRAVA_CLIENT_ID", "12345")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "environment-test-secret")
    monkeypatch.setenv(
        "STRAVA_REDIRECT_URI",
        "http://127.0.0.1:8000/integrations/strava/callback",
    )
    monkeypatch.setenv(
        "STRAVA_AUTHORIZATION_URL", "https://www.strava.com/oauth/authorize"
    )
    monkeypatch.setenv("STRAVA_TOKEN_URL", "https://www.strava.com/oauth/token")
    monkeypatch.setenv("STRAVA_SCOPES", "read,activity:read_all")
    monkeypatch.setenv("OAUTH_STATE_TTL_SECONDS", "900")
    monkeypatch.setenv("OAUTH_STATE_SQLITE_PATH", "test-oauth-state.sqlite3")
    monkeypatch.setenv("OAUTH_STATE_DIAGNOSTICS", "true")
    monkeypatch.setenv(
        "TC_DATABASE_URL",
        "postgresql+psycopg://environment:password@localhost/environment",
    )

    settings = Settings(_env_file=None)

    assert settings.strava_client_id == "12345"
    assert settings.strava_client_secret == SecretStr("environment-test-secret")
    assert settings.strava_redirect_uri.endswith("/integrations/strava/callback")
    assert settings.strava_scopes == "read,activity:read_all"
    assert settings.oauth_state_ttl_seconds == 900
    assert settings.oauth_state_sqlite_path == "test-oauth-state.sqlite3"
    assert settings.oauth_state_diagnostics is True
    assert settings.database_url == (
        "postgresql+psycopg://environment:password@localhost/environment"
    )
    assert "environment-test-secret" not in repr(settings)


def test_required_strava_settings_have_no_credential_defaults(monkeypatch) -> None:
    for name in (
        "STRAVA_CLIENT_ID",
        "STRAVA_CLIENT_SECRET",
        "STRAVA_REDIRECT_URI",
        "STRAVA_SCOPES",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.strava_client_id is None
    assert settings.strava_client_secret is None
    assert settings.strava_redirect_uri is None
    assert settings.strava_scopes is None
    assert settings.strava_authorization_url == "https://www.strava.com/oauth/authorize"
    assert settings.strava_token_url == "https://www.strava.com/oauth/token"
    assert settings.oauth_state_ttl_seconds == 600
    assert settings.oauth_state_sqlite_path is None
    assert settings.oauth_state_diagnostics is False


def test_backend_dotenv_path_is_absolute_and_cwd_independent() -> None:
    assert BACKEND_ENV_FILE.is_absolute()
    assert BACKEND_ENV_FILE == (
        Path(__file__).resolve().parents[1] / ".env"
    )
    assert Settings.model_config["env_file"] == BACKEND_ENV_FILE
    assert Settings.model_config["env_file_encoding"] == "utf-8"


def test_automatic_dotenv_loading_uses_absolute_path_from_any_cwd(
    monkeypatch, tmp_path
) -> None:
    dotenv = tmp_path / "backend.env"
    dotenv.write_text(
        "TC_DATABASE_URL=postgresql+psycopg://dotenv:password@localhost/dotenv",
        encoding="utf-8",
    )
    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()

    class IsolatedSettings(Settings):
        model_config = SettingsConfigDict(
            **{
                **Settings.model_config,
                "env_file": dotenv.resolve(),
            }
        )

    monkeypatch.delenv("TC_DATABASE_URL", raising=False)
    monkeypatch.chdir(unrelated_cwd)

    settings = IsolatedSettings()

    assert settings.database_url == (
        "postgresql+psycopg://dotenv:password@localhost/dotenv"
    )


def test_database_url_accepts_existing_alembic_dotenv_key(tmp_path) -> None:
    dotenv = tmp_path / "backend.env"
    dotenv.write_text(
        "sqlalchemy.url=postgresql+psycopg://alembic:password@localhost/alembic",
        encoding="utf-8",
    )

    settings = Settings(_env_file=dotenv)

    assert settings.database_url == (
        "postgresql+psycopg://alembic:password@localhost/alembic"
    )


def test_cached_settings_uses_absolute_dotenv_source(monkeypatch, tmp_path) -> None:
    dotenv = tmp_path / "backend.env"
    dotenv.write_text(
        "TC_DATABASE_URL=postgresql+psycopg://cached:password@localhost/cached",
        encoding="utf-8",
    )
    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv.resolve())
    monkeypatch.delenv("TC_DATABASE_URL", raising=False)
    monkeypatch.chdir(unrelated_cwd)
    get_settings.cache_clear()

    try:
        first = get_settings()
        second = get_settings()
        assert first is second
        assert first.database_url == (
            "postgresql+psycopg://cached:password@localhost/cached"
        )
    finally:
        get_settings.cache_clear()
