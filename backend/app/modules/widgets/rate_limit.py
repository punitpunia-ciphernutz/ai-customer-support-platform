"""Simple in-memory rate limiter for public widget endpoints."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again shortly.",
                )
            bucket.append(now)


# Conservative defaults for public embed traffic
_session_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)
_message_limiter = SlidingWindowRateLimiter(max_requests=60, window_seconds=60)


def rate_limit_session(request: Request, public_id: str) -> None:
    ip = request.client.host if request.client else "unknown"
    _session_limiter.check(f"session:{public_id}:{ip}")


def rate_limit_message(request: Request, public_id: str) -> None:
    ip = request.client.host if request.client else "unknown"
    _message_limiter.check(f"message:{public_id}:{ip}")
