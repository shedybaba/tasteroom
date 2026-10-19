"""Guided taste input: autocomplete suggestions and "need ideas?" chips, both straight from Qloo.

/api/suggest proxies Qloo /search for the slot's entity types. /api/ideas asks /v2/insights for popular
entities of the slot's type (no taste signal needed; verified live), so a member who doesn't know what to
type can tap an idea. Both return slim, frontend-ready suggestions."""
import logging
from typing import Literal

from pydantic import BaseModel

from .allowed_params import ARTIST, BRAND, PLACE, PODCAST, TV_SHOW
from .baseline import _city_matches
from .explain import NOISE_TAG_NAMES
from .models import SlimEntity
from .qloo_client import QlooClient, QlooError
from .resolve import ANY_TYPES

log = logging.getLogger("tasteroom.suggest")

MOVIE = "urn:entity:movie"
SlotType = Literal["artist", "show", "brand", "podcast", "place", "any"]
IdeaType = Literal["artist", "show", "brand", "podcast", "place"]
SUGGEST_TYPES: dict[str, list[str]] = {
    "artist": [ARTIST], "show": [TV_SHOW, MOVIE], "brand": [BRAND], "podcast": [PODCAST], "place": [PLACE],
    "any": ANY_TYPES,
}
MAX_SUGGESTIONS = 6
IDEAS_TAKE = 8
IDEAS_MIN_POPULARITY = 0.9
IDEAS_FALLBACK_POPULARITY = 0.7  # small cities may have too few places above 0.9

# Verified live (API_FINDINGS.md): a union of these gives hangout spots; a bare locality query returns hotels.
HANGOUT_TAGS = ["urn:tag:genre:place:restaurant:bar", "urn:tag:genre:place:lounge", "urn:tag:genre:place:restaurant"]

# Used only if Qloo is unreachable. Names only (no ids), so they resolve through the normal flow later.
STATIC_IDEAS: dict[str, list[tuple[str, str]]] = {
    "artist": [("Burna Boy", "urn:entity:artist"), ("Beyoncé", "urn:entity:artist"), ("Drake", "urn:entity:artist"),
               ("Taylor Swift", "urn:entity:artist"), ("Wizkid", "urn:entity:artist"), ("Rihanna", "urn:entity:artist"),
               ("The Weeknd", "urn:entity:artist"), ("Bad Bunny", "urn:entity:artist")],
    "show": [("Stranger Things", TV_SHOW), ("Money Heist", TV_SHOW), ("The Office", TV_SHOW), ("Squid Game", TV_SHOW),
             ("Inception", MOVIE), ("Black Mirror", TV_SHOW), ("Breaking Bad", TV_SHOW), ("Interstellar", MOVIE)],
    "brand": [("Nike", BRAND), ("Apple", BRAND), ("Adidas", BRAND), ("Spotify", BRAND), ("Netflix", BRAND),
              ("Zara", BRAND), ("Samsung", BRAND), ("Coca-Cola", BRAND)],
    "podcast": [("Call Her Daddy", PODCAST), ("The Joe Rogan Experience", PODCAST), ("Crime Junkie", PODCAST),
                ("The Daily", PODCAST), ("Huberman Lab", PODCAST), ("My Favorite Murder", PODCAST),
                ("The Diary Of A CEO", PODCAST), ("How I Built This", PODCAST)],
}


class Suggestion(BaseModel):
    id: str | None = None           # None for static fallback ideas (resolved by name later)
    name: str
    type: str                       # entity urn, e.g. urn:entity:artist
    image: str | None = None
    description: str | None = None
    subtitle: str | None = None     # city for venues, first meaningful tag otherwise (tells namesakes apart)


class IdeasResponse(BaseModel):
    type: str
    source: Literal["qloo", "static", "none"]
    ideas: list[Suggestion]
    needs_city: bool = False        # place ideas need a city that resolves to a Qloo locality


def _short(text: str | None, limit: int = 110) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def to_suggestion(e: SlimEntity) -> Suggestion:
    tag = next((t for t in e.tags if t.lower() not in NOISE_TAG_NAMES), None)
    return Suggestion(id=e.id, name=e.name, type=e.type, image=e.image, description=_short(e.description),
                      subtitle=e.city if e.type == PLACE and e.city else tag)


def clean_query(q: str) -> str:
    """Control characters (newlines, NULs) become word separators; whitespace is collapsed."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in q).split())


async def suggest(client: QlooClient, q: str, slot: str, city: str = "") -> list[Suggestion]:
    q = clean_query(q)
    if len(q) < 2:
        return []
    local = slot in ("place", "any") and bool(city.strip())
    # Qloo search is global. For venues, over-fetch and float the ones in the organizer's city to the top.
    found = await client.search(q, SUGGEST_TYPES[slot], take=15 if local else MAX_SUGGESTIONS)
    if local:
        found = sorted(found, key=lambda e: 0 if e.type == PLACE and _city_matches(e.city, [city]) else 1)
    return [to_suggestion(e) for e in found if e.name][:MAX_SUGGESTIONS]


def _interleave(*lists: list[SlimEntity], limit: int) -> list[SlimEntity]:
    out, seen = [], set()
    for i in range(max((len(x) for x in lists), default=0)):
        for x in lists:
            if i < len(x) and x[i].id not in seen:
                seen.add(x[i].id)
                out.append(x[i])
    return out[:limit]


def _static(slot: str) -> IdeasResponse:
    items = [Suggestion(name=n, type=t) for n, t in STATIC_IDEAS.get(slot, [])]
    return IdeasResponse(type=slot, source="static" if items else "none", ideas=items)


async def _popular(client: QlooClient, entity_type: str, **extra) -> list[SlimEntity]:
    params = {"filter.type": entity_type, "filter.popularity.min": IDEAS_MIN_POPULARITY, "take": IDEAS_TAKE, **extra}
    return (await client.insights(params)).entities


async def ideas(client: QlooClient, slot: str, city: str = "") -> IdeasResponse:
    try:
        if slot == "place":
            if not city.strip():
                return IdeasResponse(type=slot, source="none", ideas=[], needs_city=True)
            loc = await client.find_locality(city)
            if loc is None:
                return IdeasResponse(type=slot, source="none", ideas=[], needs_city=True)
            found = await _popular(client, PLACE, **{"filter.location": loc.id, "filter.tags": HANGOUT_TAGS})
            if len(found) < 4:
                found = await _popular(client, PLACE, **{"filter.location": loc.id, "filter.tags": HANGOUT_TAGS,
                                                         "filter.popularity.min": IDEAS_FALLBACK_POPULARITY})
        elif slot == "show":
            found = _interleave(await _popular(client, TV_SHOW), await _popular(client, MOVIE), limit=IDEAS_TAKE)
        else:
            found = await _popular(client, SUGGEST_TYPES[slot][0])
        found = [e for e in found if e.name and e.image]
        if not found:
            return _static(slot)
        return IdeasResponse(type=slot, source="qloo", ideas=[to_suggestion(e) for e in found[:IDEAS_TAKE]])
    except QlooError as exc:
        log.warning("ideas(%s) failed: status=%s; using static list", slot, exc.status)
        return _static(slot) if slot != "place" else IdeasResponse(type=slot, source="none", ideas=[])
