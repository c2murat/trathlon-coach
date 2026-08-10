from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable


@dataclass(frozen=True, slots=True)
class LoginRateLimitPolicy:
    max_failures: int
    window_seconds: int
    max_keys: int


class InMemoryLoginRateLimiter:
    """Process-local limiter with a replaceable application-facing interface."""

    def __init__(self, policy: LoginRateLimitPolicy, *, clock: Callable[[], float] = monotonic) -> None:
        self.policy = policy
        self._clock = clock
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def is_limited(self, key: str) -> bool:
        with self._lock:
            attempts = self._active_attempts(key)
            return len(attempts) >= self.policy.max_failures

    def record_failure(self, key: str) -> None:
        with self._lock:
            attempts = self._active_attempts(key)
            attempts.append(self._clock())
            self._attempts[key] = attempts
            self._attempts.move_to_end(key)
            self._evict_excess()

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def cleanup(self) -> int:
        with self._lock:
            before = len(self._attempts)
            for key in list(self._attempts):
                self._active_attempts(key)
            return before - len(self._attempts)

    def _active_attempts(self, key: str) -> deque[float]:
        cutoff = self._clock() - self.policy.window_seconds
        attempts = self._attempts.get(key, deque())
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if attempts:
            self._attempts[key] = attempts
        else:
            self._attempts.pop(key, None)
        return attempts

    def _evict_excess(self) -> None:
        while len(self._attempts) > self.policy.max_keys:
            self._attempts.popitem(last=False)