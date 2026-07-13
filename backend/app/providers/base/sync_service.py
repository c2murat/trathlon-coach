from abc import ABC, abstractmethod
from typing import Generic, TypeVar


SyncRequestT = TypeVar("SyncRequestT")
SyncResultT = TypeVar("SyncResultT")


class SyncService(ABC, Generic[SyncRequestT, SyncResultT]):
    """Coordinate provider synchronization through an application-owned request.

    Future implementations will orchestrate bounded imports, checkpoints,
    deduplication, rate-limit pauses, retries, and progress reporting. They will
    call provider clients and mappers through their contracts while application
    services retain transaction and job-lifecycle control.

    This interface defines no scheduling, persistence, network, or retry logic.
    Its request/result types remain opaque until the synchronization sprint.
    """

    @abstractmethod
    async def synchronize(self, request: SyncRequestT) -> SyncResultT:
        """Execute one provider-neutral synchronization request."""

