"""Per-IP limit for the endpoints that cost money (live Qloo + OpenAI calls). Uses the `limits`
library that slowapi is built on, but is hit manually so cache hits do not consume the quota."""
from fastapi import Request
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from .config import settings

_limiter = MovingWindowRateLimiter(MemoryStorage())
_item = parse(settings.rate_limit_plan)
_suggest_item = parse(settings.rate_limit_suggest)
_rooms_item = parse(settings.rate_limit_rooms)
_join_item = parse(settings.rate_limit_join)
_read_item = parse(settings.rate_limit_room_read)


def client_ip(request: Request) -> str:
    """The visitor's address behind the host's proxy. Railway documents X-Real-IP as the client's remote
    IP (the edge sets it). Otherwise fall back to the LAST X-Forwarded-For entry: proxies append the
    address they saw, so the last one is the one a caller cannot forge. Locally, the socket address."""
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def allow(request: Request) -> bool:
    return _limiter.hit(_item, "plan", client_ip(request))


def allow_suggest(request: Request) -> bool:
    """Autocomplete / ideas lookups: a separate, per-minute bucket so typing never eats the plan quota."""
    return _limiter.hit(_suggest_item, "suggest", client_ip(request))


def allow_rooms(request: Request) -> bool:
    return _limiter.hit(_rooms_item, "rooms", client_ip(request))


def allow_join(request: Request) -> bool:
    return _limiter.hit(_join_item, "join", client_ip(request))


def allow_room_read(request: Request) -> bool:
    return _limiter.hit(_read_item, "room_read", client_ip(request))


def reset() -> None:  # tests
    _limiter.storage.reset()
