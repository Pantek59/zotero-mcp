import hashlib
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from zotero_mcp.credentials import ZOTERO_API_KEY_HEADER

_DEFAULT_WINDOW_SECONDS = 60
_DEFAULT_MAX_REQUESTS = 60


class _Bucket:
    __slots__ = ("count", "window_start")

    def __init__(self, window_start: float) -> None:
        self.count = 1
        self.window_start = window_start


class RateLimiter:
    def __init__(
        self,
        max_requests: int = _DEFAULT_MAX_REQUESTS,
        window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._buckets: dict[str, _Bucket] = {}

    def check(self, api_key: str) -> bool:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        now = time.monotonic()
        bucket = self._buckets.get(key_hash)

        if bucket is None:
            self._buckets[key_hash] = _Bucket(now)
            return True

        if now - bucket.window_start >= self._window_seconds:
            bucket.count = 1
            bucket.window_start = now
            return True

        bucket.count += 1
        return bucket.count <= self._max_requests

    def clear(self) -> None:
        self._buckets.clear()


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


class RateLimitMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        api_key = request.headers.get(ZOTERO_API_KEY_HEADER)

        if api_key:
            limiter = get_rate_limiter()
            if not limiter.check(api_key):
                response = JSONResponse(
                    {"error": "Rate limit exceeded. Please try again later."},
                    status_code=429,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
