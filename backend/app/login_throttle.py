"""Limits repeated failed logins: an attacker guessing passwords is slowed, and PBKDF2 cannot be used to tie up the CPU."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

MAX_FAILURES = 5
WINDOW_S = 60.0
_MAX_TRACKED = 10_000


class LoginThrottle:
    """Counts failed logins per (client address, username) in a sliding window. In memory: it resets on restart and is
    per process, which is enough for a single-instance prototype."""

    def __init__(
        self,
        max_failures: int = MAX_FAILURES,
        window_s: float = WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window_s
        self._clock = clock
        self._failures: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(client: str, username: str) -> tuple[str, str]:
        return client, username.strip().lower()

    def _recent(self, key: tuple[str, str], now: float) -> deque[float]:
        times = self._failures.get(key)
        if times is None:
            return deque()
        while times and now - times[0] >= self._window:
            times.popleft()
        if not times:
            del self._failures[key]
            return deque()
        return times

    def retry_after(self, client: str, username: str) -> int:
        """Seconds to wait before this client may try this username again; 0 if it may try now."""
        key = self._key(client, username)
        with self._lock:
            now = self._clock()
            times = self._recent(key, now)
            if len(times) < self._max:
                return 0
            return max(1, int(self._window - (now - times[0])) + 1)

    def record_failure(self, client: str, username: str) -> None:
        key = self._key(client, username)
        with self._lock:
            now = self._clock()
            if len(self._failures) >= _MAX_TRACKED and key not in self._failures:
                for k in list(self._failures):  # drop expired entries so the table cannot grow without bound
                    self._recent(k, now)
                if len(self._failures) >= _MAX_TRACKED:
                    return
            self._failures.setdefault(key, deque()).append(now)

    def record_success(self, client: str, username: str) -> None:
        with self._lock:
            self._failures.pop(self._key(client, username), None)
