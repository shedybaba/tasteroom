"""Member tastes -> Qloo entities, and city -> locality."""
import asyncio
import logging

from .models import Member, ResolvedTaste, SlimEntity, Taste
from .qloo_client import QlooClient, QlooError
from .textmatch import MIN_SIMILARITY, norm as _norm, similarity  # noqa: F401  (re-exported)

log = logging.getLogger("tasteroom.resolve")

KIND_TO_TYPE = {
    "artist": "urn:entity:artist", "tv_show": "urn:entity:tv_show", "movie": "urn:entity:movie",
    "brand": "urn:entity:brand", "place": "urn:entity:place", "podcast": "urn:entity:podcast",
    "book": "urn:entity:book", "video_game": "urn:entity:videogame",  # /search spelling: no underscore
}
# Untyped retry is limited to these so a name can't resolve to a locality, person or audience.
ANY_TYPES = list(KIND_TO_TYPE.values())
SEARCH_TAKE = 5


def pick_best(query: str, candidates: list[SlimEntity]) -> SlimEntity | None:
    """Best name similarity first (in 0.05 steps), then popularity. None if nothing is close enough."""
    scored = [(similarity(query, c.name), c) for c in candidates]
    scored = [(s, c) for s, c in scored if s >= MIN_SIMILARITY]
    if not scored:
        return None
    scored.sort(key=lambda sc: (round(sc[0] / 0.05), sc[1].popularity or 0), reverse=True)
    return scored[0][1]


async def resolve_taste(client: QlooClient, taste: Taste) -> SlimEntity | None:
    text = taste.text.strip()
    if not text:
        return None
    types = [KIND_TO_TYPE[taste.kind]] if taste.kind in KIND_TO_TYPE else ANY_TYPES
    found = pick_best(text, await client.search(text, types, take=SEARCH_TAKE))
    if found is None and taste.kind in KIND_TO_TYPE:  # typed miss: retry across all content types
        found = pick_best(text, await client.search(text, ANY_TYPES, take=SEARCH_TAKE))
    return found


async def resolve_members(client: QlooClient, members: list[Member]) -> list[ResolvedTaste]:
    """Resolve every (member, taste). Identical inputs are searched once. A Qloo error leaves that
    taste unresolved (the UI shows it as amber) instead of failing the whole request."""
    memo: dict[tuple[str, str], asyncio.Task] = {}

    async def one(taste: Taste) -> tuple[SlimEntity | None, bool]:
        key = (_norm(taste.text), taste.kind)
        if key not in memo:
            memo[key] = asyncio.ensure_future(resolve_taste(client, taste))
        try:
            return await memo[key], False
        except QlooError as exc:
            log.warning("resolve failed for %r: status=%s", taste.text, exc.status)
            return None, True

    pairs = [(m.name, t) for m in members for t in m.tastes]
    results = await asyncio.gather(*(one(t) for _, t in pairs))
    return [ResolvedTaste(member=name, input=t.text, entity=e, lookup_failed=failed)
            for (name, t), (e, failed) in zip(pairs, results)]


async def resolve_city(client: QlooClient, city: str) -> SlimEntity | None:
    try:
        return await client.find_locality(city.strip()) if city.strip() else None
    except QlooError as exc:
        log.warning("locality lookup failed for %r: %s", city, exc)
        return None
