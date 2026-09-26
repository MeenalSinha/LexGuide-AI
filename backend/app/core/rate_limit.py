"""
Rate limiting.

Prototype uses a simple in-memory sliding-window limiter keyed by client IP.
Production note: swap for a Redis-backed limiter (e.g. via slowapi or a
custom Redis INCR+EXPIRE) once running more than one backend replica, since
in-memory state does not share across processes. Interface/behavior would
stay identical to callers.
"""
import time
from collections import defaultdict, deque
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.config import settings


class RateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = defaultdict(deque)  # ip -> deque[timestamps], instance-scoped

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        window = self._hits[key]
        while window and now - window[0] > self.window_seconds:
            window.popleft()
        if len(window) >= self.max_requests:
            return False
        window.append(now)
        return True


_limiter = RateLimiter(max_requests=settings.RATE_LIMIT_PER_MINUTE, window_seconds=60)


async def rate_limit_middleware(request: Request, call_next):
    # Health checks and docs are exempt so uptime probes never get throttled.
    if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    if not _limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down and try again shortly."},
        )
    return await call_next(request)
