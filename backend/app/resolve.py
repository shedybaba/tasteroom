"""Member tastes -> Qloo entities, and city -> locality."""
import asyncio
import logging
import re
import unicodedata
from difflib import SequenceMatcher

from .models import Member, ResolvedTaste, SlimEntity, Taste
from .qloo_client import QlooClient, QlooError

log = logging.getLogger("tasteroom.resolve")

KIND_TO_TYPE = {
    "artist": "urn:entity:artist", "tv_show": "urn:entity:tv_show", "movie": "urn:entity:movie",
    "brand": "urn:entity:brand", "place": "urn:entity:place", "podcast": "urn:entity:podcast",
    "book": "urn:entity:book", "video_game": "urn:entity:videogame",  # /search spelling: no underscore
}
# Untyped retry is limited to these so a name can't resolve to a locality, person or audience.
ANY_TYPES = list(KIND_TO_TYPE.values())
MIN_SIMILARITY = 0.75  # 0.6-0.7 let 'Kenshi Yonezu' resolve to 'Kenshin'
SEARCH_TAKE = 5


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def similarity(query: str, name: str) -> float:
    a, b = _norm(query), _norm(name)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    if b.startswith(a):  # "Nike" -> "Nike Training Club" is a decent match; the reverse (a truncated
        ratio = max(ratio, 0.85)  # candidate like "Kenshi" for "Kenshi Yonezu") is not
    return ratio


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

    async def one(taste: Taste) -> SlimEntity | None:
        key = (_norm(taste.text), taste.kind)
        if key not in memo:
            memo[key] = asyncio.ensure_future(resolve_taste(client, taste))
        try:
            return await memo[key]
        except QlooError as exc:
            log.warning("resolve failed for %r: %s", taste.text, exc)
            return None

    pairs = [(m.name, t) for m in members for t in m.tastes]
    entities = await asyncio.gather(*(one(t) for _, t in pairs))
    return [ResolvedTaste(member=name, input=t.text, entity=e) for (name, t), e in zip(pairs, entities)]


async def resolve_city(client: QlooClient, city: str) -> SlimEntity | None:
    try:
        return await client.find_locality(city.strip()) if city.strip() else None
    except QlooError as exc:
        log.warning("locality lookup failed for %r: %s", city, exc)
        return None
