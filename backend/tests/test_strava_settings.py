from pydantic import SecretStr

from app.core.settings import Settings


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

    settings = Settings(_env_file=None)

    assert settings.strava_client_id == "12345"
    assert settings.strava_client_secret == SecretStr("environment-test-secret")
    assert settings.strava_redirect_uri.endswith("/integrations/strava/callback")
    assert settings.strava_scopes == "read,activity:read_all"
    assert settings.oauth_state_ttl_seconds == 900
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
