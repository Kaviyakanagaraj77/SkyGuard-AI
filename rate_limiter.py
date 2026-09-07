"""
SkyGuard AI v2 - Lightweight Rate Limiting & Abuse Protection (Phase 5)
------------------------------------------------------------------------
Provides an in-memory sliding window rate limiter for login and administrative routes
to prevent brute-force attacks without requiring external Redis dependencies.
"""

import time
from typing import Dict, List
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_key: str) -> bool:
        """
        Checks if the client_key is within the allowed request rate limit.
        Cleans up expired timestamps in the window.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Filter out timestamps older than current window
        self.requests[client_key] = [ts for ts in self.requests[client_key] if ts > cutoff]

        if len(self.requests[client_key]) >= self.max_requests:
            return False

        self.requests[client_key].append(now)
        return True

    def reset(self, client_key: str):
        """Resets the rate limit tracker for a client_key."""
        if client_key in self.requests:
            del self.requests[client_key]


login_rate_limiter = RateLimiter(max_requests=15, window_seconds=60)
