import asyncio
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by client IP.

    In production, swap for a Redis-backed implementation if running
    multiple backend replicas behind a load balancer.
    """

    def __init__(self, app):
        super().__init__(app)
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._rpm = settings.RATE_LIMIT_RPM

    async def dispatch(self, request: Request, call_next):
        if request.url.path != "/chat":
            return await call_next(request)

        key = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - 60

        async with self._lock:
            timestamps = self._windows[key]
            self._windows[key] = [t for t in timestamps if t > cutoff]
            if len(self._windows[key]) >= self._rpm:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please wait before sending more messages."},
                )
            self._windows[key].append(now)

        return await call_next(request)
