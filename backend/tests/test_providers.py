import inspect

import pytest

from app.providers.base import (
    ActivityMapper,
    AuthenticationError,
    AuthorizationError,
    InvalidPayloadError,
    OAuthProvider,
    Provider,
    ProviderError,
    RateLimitError,
    SyncService,
    TemporaryProviderError,
    WebhookService,
)
from app.providers.strava import StravaProvider


@pytest.mark.parametrize(
    "interface",
    [Provider, OAuthProvider, ActivityMapper, SyncService, WebhookService],
)
def test_provider_contracts_are_abstract(interface: type[object]) -> None:
    assert inspect.isabstract(interface)
    with pytest.raises(TypeError):
        interface()


def test_oauth_provider_inherits_provider_interface() -> None:
    assert issubclass(OAuthProvider, Provider)


def test_strava_provider_implements_provider_metadata() -> None:
    provider = StravaProvider()

    assert isinstance(provider, Provider)
    assert not isinstance(provider, OAuthProvider)
    assert provider.provider_name == "strava"
    assert provider.display_name == "Strava"
    assert provider.supported_features == frozenset(
        {
            "oauth",
            "historical_activity_import",
            "activity_webhooks",
            "token_refresh",
        }
    )
    assert provider.supported_activity_types == frozenset(
        {"swimming", "cycling", "running", "strength", "other"}
    )


def test_strava_provider_metadata_is_immutable() -> None:
    provider = StravaProvider()

    assert isinstance(provider.supported_features, frozenset)
    assert isinstance(provider.supported_activity_types, frozenset)


def test_provider_exception_hierarchy() -> None:
    assert issubclass(AuthenticationError, ProviderError)
    assert issubclass(AuthorizationError, ProviderError)
    assert issubclass(TemporaryProviderError, ProviderError)
    assert issubclass(RateLimitError, TemporaryProviderError)
    assert issubclass(InvalidPayloadError, ProviderError)


def test_provider_interfaces_have_responsibility_docstrings() -> None:
    for interface in (
        Provider,
        OAuthProvider,
        ActivityMapper,
        SyncService,
        WebhookService,
    ):
        assert inspect.getdoc(interface)
        assert len(inspect.getdoc(interface).split()) >= 20
