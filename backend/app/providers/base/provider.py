from abc import ABC, abstractmethod
from collections.abc import Set


class Provider(ABC):
    """Describe an external platform without invoking it.

    A provider is the smallest common contract shared by every external
    integration. Its metadata lets the application discover a stable provider
    identifier, present a human-readable name, and determine planned
    capabilities and canonical activity categories.

    This interface deliberately contains no HTTP client, credentials, tokens,
    persistence access, or synchronization behavior. Those responsibilities
    belong to narrower provider interfaces and concrete adapters.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable, lowercase identifier used in internal records."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Return the provider name suitable for user-interface labels."""

    @property
    @abstractmethod
    def supported_features(self) -> Set[str]:
        """Return immutable capability identifiers advertised by the adapter.

        Capability metadata describes intended adapter support; it does not
        imply that a later sprint's OAuth, webhook, or synchronization behavior
        is already implemented or enabled.
        """

    @property
    @abstractmethod
    def supported_activity_types(self) -> Set[str]:
        """Return provider-neutral activity categories the adapter can map."""

