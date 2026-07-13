class ProviderError(Exception):
    """Base class for safe failures raised at an external-provider boundary."""


class AuthenticationError(ProviderError):
    """The provider could not authenticate the application or authorization."""


class AuthorizationError(ProviderError):
    """The provider denied access or the granted authorization is insufficient."""


class TemporaryProviderError(ProviderError):
    """A transient provider or network condition may succeed on a later retry."""


class RateLimitError(TemporaryProviderError):
    """The provider rate budget is exhausted and work must be deferred."""


class InvalidPayloadError(ProviderError):
    """A provider payload cannot be validated or mapped safely."""

