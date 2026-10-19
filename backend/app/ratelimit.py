"""Per-IP limit for the endpoints that cost money (live Qloo + OpenAI calls). Uses the `limits`
library that slowapi is built on, but is hit manually so cache hits do not consume the quota."""
from fastapi import Request
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from .config import settings

_limiter = MovingWindowRateLimiter(MemoryStorage())
_item = parse(settings.rate_limit_plan)


def client_ip(request: Request) -> str:
    # Behind Render's proxy request.client is the proxy. The platform appends the real client address
    # to X-Forwarded-For, so the LAST entry is the one a caller cannot forge.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def allow(request: Request) -> bool:
    return _limiter.hit(_item, "plan", client_ip(request))


def reset() -> None:  # tests
    _limiter.storage.reset()
