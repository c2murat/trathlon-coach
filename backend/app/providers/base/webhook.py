from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Generic, TypeVar


WebhookReceiptT = TypeVar("WebhookReceiptT")


class WebhookService(ABC, Generic[WebhookReceiptT]):
    """Define provider webhook validation and durable-receipt responsibilities.

    A future adapter will validate subscription challenges, parse a bounded
    notification envelope, derive an idempotency identity, and return a receipt
    suitable for fast acknowledgement. Full activity retrieval and processing
    occur later in background synchronization, not in webhook receipt.

    This sprint provides only the contract. It does not validate requests,
    accept payloads, enqueue jobs, or process events.
    """

    @abstractmethod
    def validate_subscription(
        self, query_parameters: Mapping[str, str]
    ) -> Mapping[str, str]:
        """Validate a provider challenge and return its safe response fields."""

    @abstractmethod
    async def receive_event(
        self, payload: Mapping[str, object]
    ) -> WebhookReceiptT:
        """Describe durable receipt of one bounded provider notification."""

