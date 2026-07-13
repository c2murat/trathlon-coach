"""External provider contracts and provider-specific adapters.

Application and domain code should depend on interfaces from :mod:`app.providers.base`.
Concrete adapters, such as Strava, live in provider-specific subpackages.
"""

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

__all__ = [
    "ActivityMapper",
    "AuthenticationError",
    "AuthorizationError",
    "InvalidPayloadError",
    "OAuthProvider",
    "Provider",
    "ProviderError",
    "RateLimitError",
    "SyncService",
    "TemporaryProviderError",
    "WebhookService",
]

