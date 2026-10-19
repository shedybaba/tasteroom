"""All HTTP to Qloo lives here: auth, retries, caching, 404 -> empty, and mock mode.

Mock mode (no QLOO_API_KEY) serves saved responses from backend/samples/ so the UI and tests
work offline. Live mode never logs or returns the API key.
"""
import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import cache
from .allowed_params import clean_params
from .config import settings
from .models import SlimEntity
from .slim import slim_entity
from .textmatch import MIN_SIMILARITY, norm, similarity

log = logging.getLogger("tasteroom.qloo")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
MAX_RETRIES = 5
# Measured live: 6 parallel requests never hit a 429 (90 tastes in ~25 s); 10 did (10 of 90 failed after retries).
CONCURRENCY = 6


class QlooError(Exception):
    """Raised for non-recoverable Qloo failures. Messages never include credentials."""

    def __init__(self, status: int, message: str):
        super().__init__(f"Qloo {status}: {message}")
        self.status = status


@dataclass
class Response:
    status: int
    body: Any


@dataclass
class InsightsResult:
    entities: list[SlimEntity]
    # Top-level query.explainability (aggregate effect of each input entity), if returned.
    explainability: dict[str, Any] = field(default_factory=dict)
    dropped_params: list[str] = field(default_factory=list)


def _short(urn: str) -> str:
    return urn.rsplit(":", 1)[-1]


def _locality_matches(head: str, raw: dict[str, Any]) -> bool:
    if similarity(head, raw.get("name", "")) >= MIN_SIMILARITY:
        return True
    h = norm(head)
    for aka in (raw.get("properties") or {}).get("akas") or []:
        value = aka.get("value", "")
        first = value.split(",")[0]
        if similarity(head, first) >= MIN_SIMILARITY or norm(first).startswith(h + " "):
            return True
    return False


class QlooClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, mock: bool | None = None):
        self.api_key = settings.qloo_api_key if api_key is None else api_key
        self.base_url = (base_url or settings.qloo_base_url).rstrip("/")
        self.mock = (not self.api_key) if mock is None else mock
        self._http: httpx.AsyncClient | None = None
        self._sem = asyncio.Semaphore(CONCURRENCY)

    async def aclose(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # ---- low level -------------------------------------------------------------------------

    async def request(
        self, path: str, params: dict[str, Any], *, use_cache: bool = True, ttl: int = cache.DAY
    ) -> Response:
        """GET with retries on 429/5xx. Returns the status for anything else (caller decides)."""
        if self.mock:
            return self._mock(path, params)

        key = cache.make_key(path, params)
        if use_cache:
            hit = cache.get(key)
            if hit is not None:
                return Response(200, hit)

        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url, headers={"X-Api-Key": self.api_key}, timeout=30
            )
        resp: httpx.Response | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with self._sem:
                    resp = await self._http.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt == MAX_RETRIES:
                    raise QlooError(0, f"network error: {type(exc).__name__}") from exc
            else:
                if resp.status_code != 429 and resp.status_code < 500:
                    break
                if attempt == MAX_RETRIES:
                    break
            retry_after = resp.headers.get("Retry-After") if resp is not None else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            await asyncio.sleep(delay + random.random() * 0.3)
        assert resp is not None
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:300]}
        if resp.status_code == 200 and use_cache:
            cache.put(key, body, ttl)
        return Response(resp.status_code, body)

    async def _get(self, path: str, params: dict[str, Any], **kw: Any) -> Any:
        """Like request() but raises on errors and maps 404 (= no results) to None."""
        r = await self.request(path, params, **kw)
        if r.status == 404:
            return None
        if r.status != 200:
            msg = r.body.get("message") or r.body.get("error") if isinstance(r.body, dict) else None
            raise QlooError(r.status, str(msg or "request failed")[:200])
        return r.body

    # ---- mock mode ---------------------------------------------------------------------------

    def _mock(self, path: str, params: dict[str, Any]) -> Response:
        if path == "/search":
            types = _short(str(params.get("types", "any")).split(",")[0])
            name = f"search_{types}.json"
        elif path == "/v2/insights":
            name = f"insights_{_short(str(params.get('filter.type', 'artist')))}.json"
        elif path == "/entities":
            name = "entities.json"
        else:
            name = f"{path.rsplit('/', 1)[-1]}.json"  # /v2/tags -> tags.json
        f = SAMPLES / name
        if not f.exists():
            return Response(404, {"message": f"no mock sample {name}"})
        body = json.loads(f.read_text())
        if path == "/search" and params.get("query"):
            q = str(params["query"]).lower()
            hits = [e for e in body.get("results", []) if q in e.get("name", "").lower()]
            body = {**body, "results": hits or body.get("results", [])[:1]}
        return Response(200, body)

    # ---- typed helpers -----------------------------------------------------------------------

    async def search(
        self, query: str, types: list[str] | None = None, take: int = 3, **extra: Any
    ) -> list[SlimEntity]:
        params: dict[str, Any] = {"query": query, "take": take, **extra}
        if types:
            params["types"] = ",".join(types)
        body = await self._get("/search", params)
        return [slim_entity(e) for e in (body or {}).get("results", [])]

    async def find_locality(self, city: str) -> SlimEntity | None:
        """City name -> Qloo locality, or None. Qloo's search is fuzzy ("Zzyzx Atlantis Narnia" returns a
        locality called "Atlantis"), so a hit only counts if its name or one of its aliases matches what was
        typed. Aliases matter: Abuja is filed as "Federal Capital Territory" with the alias "Abuja Federal
        Capital Territory". Candidates stay in Qloo's relevance order (so "Lagos" is the state, not a street)."""
        head = city.split(",")[0].strip()
        if not head:
            return None
        body = await self._get("/search", {"query": city, "types": "urn:entity:locality", "take": 5})
        for raw in (body or {}).get("results", []):
            if _locality_matches(head, raw):
                return slim_entity(raw)
        return None

    async def get_entities(self, ids: list[str]) -> list[SlimEntity]:
        if not ids:
            return []
        body = await self._get("/entities", {"entity_ids": ",".join(ids)})
        results = (body or {}).get("results") or (body or {}).get("entities") or []
        if isinstance(results, dict):
            results = results.get("entities", [])
        return [slim_entity(e) for e in results]

    async def find_tags(self, query: str, take: int = 10, **extra: Any) -> list[dict[str, Any]]:
        body = await self._get("/v2/tags", {"filter.query": query, "take": take, **extra})
        res = (body or {}).get("results", {})
        tags = res.get("tags", []) if isinstance(res, dict) else res
        return [t for t in tags if isinstance(t, dict)]

    async def find_audiences(
        self, query: str, parent_type: str | None = None, take: int = 10
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"filter.query": query, "take": take}
        if parent_type:
            params["filter.parents.types"] = parent_type
        body = await self._get("/v2/audiences", params)
        res = (body or {}).get("results", {})
        auds = res.get("audiences", []) if isinstance(res, dict) else res
        return [a for a in auds if isinstance(a, dict)]

    async def insights(self, params: dict[str, Any], *, test_mode: bool = False) -> InsightsResult:
        """Whitelisted /v2/insights call. `params` must include filter.type."""
        cleaned, dropped = clean_params(params, test_mode=test_mode)
        body = await self._get("/v2/insights", cleaned) or {}
        res = body.get("results") or {}
        entities = res.get("entities", []) if isinstance(res, dict) else []
        return InsightsResult(
            entities=[slim_entity(e) for e in entities],
            explainability=(body.get("query") or {}).get("explainability") or {},
            dropped_params=dropped,
        )
