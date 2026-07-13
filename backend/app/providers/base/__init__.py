"""Provider-neutral interfaces and safe provider exception categories."""

from app.providers.base.activity_mapper import ActivityMapper
from app.providers.base.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InvalidPayloadError,
    ProviderError,
    RateLimitError,
    TemporaryProviderError,
)
from app.providers.base.http_transport import (
    AsyncHttpTransport,
    HttpBasicAuth,
    HttpResponse,
    HttpTimeout,
    HttpxAsyncTransport,
)
from app.providers.base.oauth import OAuthProvider
from app.providers.base.oauth_state import (
    InMemoryOAuthStateStore,
    OAuthState,
    OAuthStateError,
    OAuthStateExpiredError,
    OAuthStateMissingError,
    OAuthStateReusedError,
    OAuthStateStorageError,
    OAuthStateStore,
    OAuthStateUserMismatchError,
    SQLiteOAuthStateStore,
    generate_oauth_state,
    utc_now,
)
from app.providers.base.provider import Provider
from app.providers.base.sync_service import SyncService
from app.providers.base.webhook import WebhookService

__all__ = [
    "ActivityMapper",
    "AsyncHttpTransport",
    "AuthenticationError",
    "HttpBasicAuth",
    "HttpResponse",
    "HttpTimeout",
    "HttpxAsyncTransport",
    "AuthorizationError",
    "InMemoryOAuthStateStore",
    "InvalidPayloadError",
    "OAuthProvider",
    "OAuthState",
    "OAuthStateError",
    "OAuthStateExpiredError",
    "OAuthStateMissingError",
    "OAuthStateReusedError",
    "OAuthStateStorageError",
    "OAuthStateStore",
    "OAuthStateUserMismatchError",
    "SQLiteOAuthStateStore",
    "Provider",
    "ProviderError",
    "RateLimitError",
    "SyncService",
    "TemporaryProviderError",
    "WebhookService",
    "generate_oauth_state",
    "utc_now",
]
