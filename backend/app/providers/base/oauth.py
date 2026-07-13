from abc import abstractmethod
from collections.abc import Mapping, Sequence

from app.providers.base.provider import Provider


class OAuthProvider(Provider):
    """Contract for an OAuth-capable provider adapter.

    Implementations will eventually construct authorization redirects, exchange
    authorization callbacks, refresh an existing authorization, and revoke it.
    The interface uses opaque objects for secret-bearing results so the shared
    layer does not define provider payloads or persistence models.

    Concrete implementations must validate granted scopes, keep sensitive
    values out of representations and logs, and delegate storage/encryption to
    the credential boundary. This sprint provides no implementation.
    """

    @abstractmethod
    def build_authorization_url(
        self,
        *,
        state: str,
        redirect_uri: str,
        scopes: Sequence[str],
    ) -> str:
        """Build an allow-listed authorization URL for a single-use state."""

    @abstractmethod
    async def exchange_authorization_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> object:
        """Exchange a validated callback code for an opaque authorization result."""

    @abstractmethod
    async def refresh_authorization(self, authorization: object) -> object:
        """Return a refreshed opaque authorization using provider rotation rules."""

    @abstractmethod
    async def revoke_authorization(self, authorization: object) -> None:
        """Revoke an opaque authorization without leaking sensitive values."""

    @abstractmethod
    def granted_scopes(self, authorization: object) -> Mapping[str, bool]:
        """Describe granted capabilities without exposing credential material."""

