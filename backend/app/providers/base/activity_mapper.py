from abc import ABC, abstractmethod
from typing import Generic, TypeVar


ProviderActivityT = TypeVar("ProviderActivityT")
DomainActivityT = TypeVar("DomainActivityT")


class ActivityMapper(ABC, Generic[ProviderActivityT, DomainActivityT]):
    """Convert a provider activity payload into provider-neutral domain data.

    A mapper owns field, unit, sport, timestamp, optional-value, privacy, and
    data-quality translation. It must not perform HTTP requests, commit database
    transactions, or mutate planned workouts. Unknown provider values should be
    handled according to a versioned mapping policy rather than leaking provider
    DTOs into the domain.

    Type parameters keep both the provider DTO and domain result abstract. No
    Strava payload or persistence model is introduced by this sprint.
    """

    @abstractmethod
    def map_activity(
        self,
        activity: ProviderActivityT,
        *,
        athlete_timezone: str,
    ) -> DomainActivityT:
        """Map one provider activity using the athlete's preserved timezone."""

