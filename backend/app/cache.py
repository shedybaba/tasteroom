"""Tiny disk cache shared by the Qloo client and (later) plan caching."""
import hashlib
import json
from typing import Any

from diskcache import Cache

from .config import REPO_ROOT

_cache = Cache(str(REPO_ROOT / ".cache" / "diskcache"))  # .cache/ is git-ignored

DAY = 24 * 3600


def make_key(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def get(key: str) -> Any | None:
    return _cache.get(key)


def put(key: str, value: Any, ttl: int = DAY) -> None:
    _cache.set(key, value, expire=ttl)
