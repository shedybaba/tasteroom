"""One Qloo /v2/insights query per domain, each result explained."""
import logging
from dataclasses import dataclass, field

from .allowed_params import ARTIST, BRAND, PLACE, PODCAST, TV_SHOW
from .explain import explain, relative_to_list
from .models import PlanOptions, Recommendation, SlimEntity
from .profile import Profile
from .qloo_client import QlooClient

log = logging.getLogger("tasteroom.recommend")

DOMAIN_TYPES = {
    "music": [ARTIST], "venues": [PLACE], "brands": [BRAND], "content": [PODCAST, TV_SHOW],
}
DEFAULT_TAKE = {"music": 10, "venues": 10, "brands": 10, "content": 8}
# Which of the community's entities form the signal for each domain (None = all). Measured live
# (API_FINDINGS.md): brands in the signal drag music/venue/content results toward global luxury and
# hotels; artists + shows give on-taste results. Brand sponsors are best matched from artists + brands.
SIGNAL_TYPES: dict[str, set[str] | None] = {
    "music": {"artist", "tv_show", "podcast", "movie", "book", "video_game", "place"},
    "venues": {"artist", "tv_show", "podcast", "movie", "book", "video_game", "place"},
    "content": {"artist", "tv_show", "podcast", "movie", "book", "video_game", "place"},
    "brands": {"artist", "brand"},
}
# filter.popularity.max for "hidden gems". Measured live (API_FINDINGS.md): 0.7 gives genuinely lesser-known artists,
# but brands are mostly 0.9+ already, and 0.7 turns sponsors into noise; 0.9 drops the mega-brands and keeps local ones.
HIDDEN_GEMS_MAX = {"music": 0.7, "content": 0.7, "venues": 0.7, "brands": 0.9}


MIN_TAGGED_RESULTS = 3  # a tag that yields fewer results than this is treated as "no match"


@dataclass
class DomainResult:
    domain: str
    recommendations: list[Recommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_tags: list[str] = field(default_factory=list)  # tag ids that actually shaped the results


async def find_venue_tag(client: QlooClient, kind: str) -> str | None:
    """Free text ("rooftop bar") -> a place tag id usable in filter.tags."""
    for tag in await client.find_tags(kind, take=10):
        if any(p.get("type") == PLACE for p in tag.get("parents", [])):
            return tag["id"]
    return None


def _base_params(ftype: str, signal_ids: list[str], options: PlanOptions, take: int,
                 audience_id: str | None, domain: str = "music", tags: list[str] | None = None) -> dict:
    params: dict = {
        "filter.type": ftype,
        "signal.interests.entities": signal_ids,
        "feature.explainability": True,
        "take": take,
    }
    if options.hidden_gems:
        params["filter.popularity.max"] = HIDDEN_GEMS_MAX[domain]
    if tags:
        params["filter.tags"] = tags
    if audience_id:
        params["signal.demographics.audiences"] = audience_id
    return params


async def _query(client: QlooClient, params: dict) -> list[SlimEntity]:
    return (await client.insights(params)).entities


async def recommend_venues(
    client: QlooClient, profile: Profile, *, locality: SlimEntity | None, city: str,
    options: PlanOptions, take: int = DEFAULT_TAKE["venues"], audience_id: str | None = None,
    location_id: str | None = None,
) -> DomainResult:
    """`location_id` narrows venues to one neighbourhood's locality id (instead of the whole city)."""
    out = DomainResult("venues")
    signal = profile.ids(types=SIGNAL_TYPES["venues"])
    params = _base_params(PLACE, signal, options, take, audience_id, "venues")
    # A location filter is mandatory: without one Qloo infers location from taste (API_FINDINGS.md).
    if location_id:
        params["filter.location"] = location_id
    elif locality:
        params["filter.location"] = locality.id
    elif city.strip():
        params["filter.location.query"] = city.strip()
        out.warnings.append(f"Could not resolve '{city}' to a Qloo locality; searched by city name instead.")
    else:
        out.warnings.append("No city given: venues skipped.")
        return out
    # Level 4 is "any price" but would still drop venues that have no price data, so it is not sent.
    if options.price_level_max and options.price_level_max < 4:
        params["filter.price_level.max"] = options.price_level_max
    if options.day:
        params["filter.hours"] = options.day.lower()  # best-effort: semantics unclear (API_FINDINGS.md)
    if options.venue_kind:
        tag = await find_venue_tag(client, options.venue_kind)
        if tag:
            params["filter.tags"] = tag
        else:
            out.warnings.append(f"No Qloo venue tag matched '{options.venue_kind}'; filter not applied.")

    entities = await _query(client, params)
    if not entities and "filter.tags" in params:
        out.warnings.append("No venues matched the venue type; showing venues of any type.")
        params.pop("filter.tags")
        entities = await _query(client, params)
    if not entities and location_id and locality:
        out.warnings.append("Nothing found in that neighbourhood; showing the whole city instead.")
        params["filter.location"] = locality.id
        entities = await _query(client, params)
    if not entities and locality and city.strip():
        out.warnings.append("Locality filter returned nothing; retried with the city name.")
        params.pop("filter.location")
        params["filter.location.query"] = city.strip()
        entities = await _query(client, params)
    if not entities:
        out.warnings.append("Qloo returned no venues for this city and filters.")
    out.recommendations = relative_to_list([explain(e, "venues", profile, signal) for e in entities])
    return out


SCORE_CHUNK = 40  # candidate ids per filter.results.entities call (keeps the URL short)


async def group_affinity(client: QlooClient, domain: str, profile: Profile, candidates: list[SlimEntity],
                         *, audience_id: str | None = None) -> dict[str, float]:
    """How strongly Qloo ties each candidate to the WHOLE group: the group's own signal plus filter.results.entities,
    which restricts the answer to the given entities and returns their affinity (measured live, API_FINDINGS.md).
    Candidates Qloo cannot score are simply absent from the result: never guessed."""
    signal = profile.ids(types=SIGNAL_TYPES[domain])
    by_type: dict[str, list[str]] = {}
    for e in candidates:
        by_type.setdefault(e.type, []).append(e.id)
    out: dict[str, float] = {}
    for etype, ids in by_type.items():
        for i in range(0, len(ids), SCORE_CHUNK):
            chunk = ids[i:i + SCORE_CHUNK]
            params = _base_params(etype, signal, PlanOptions(), len(chunk), audience_id, domain)
            params["filter.results.entities"] = ",".join(chunk)
            out |= {e.id: e.affinity for e in await _query(client, params) if e.affinity is not None}
    return out


async def recommend(
    client: QlooClient, domain: str, profile: Profile, *, options: PlanOptions | None = None,
    content_type: str | None = None, take: int | None = None, audience_id: str | None = None,
    tags: list[str] | None = None,
) -> DomainResult:
    """music / brands / content (venues use recommend_venues because of the location filter).
    `tags` (Qloo tag ids, e.g. a mood) restrict results; all together first, then each alone, because some
    tags exist but match nothing (measured: urn:tag:genre:music:chill returns 0 artists)."""
    options = options or PlanOptions()
    take = take or DEFAULT_TAKE[domain]
    out = DomainResult(domain)
    types = DOMAIN_TYPES[domain]
    if domain == "content" and content_type:
        types = [f"urn:entity:{content_type}"]
    signal = profile.ids(types=SIGNAL_TYPES[domain])
    async def run(tag_ids: list[str] | None) -> list[list[SlimEntity]]:
        return [await _query(client, _base_params(t, signal, options, take, audience_id, domain, tag_ids)) for t in types]

    if tags:
        for attempt in [tags] + ([[t] for t in tags] if len(tags) > 1 else []):
            batches = await run(attempt)
            if sum(len(b) for b in batches) >= MIN_TAGGED_RESULTS:
                out.used_tags = attempt
                break
        else:
            out.warnings.append("Qloo had no results for those tags, so the standard picks are shown.")
            batches = await run(None)
    else:
        batches = await run(None)
    # Interleave podcast / tv_show results so both kinds surface, then trim to `take`.
    merged: list[SlimEntity] = []
    seen: set[str] = set()
    for i in range(max((len(b) for b in batches), default=0)):
        for b in batches:
            if i < len(b) and b[i].id not in seen:
                seen.add(b[i].id)
                merged.append(b[i])
    if not merged:
        out.warnings.append(f"Qloo returned no {domain} results.")
    out.recommendations = relative_to_list([explain(e, domain, profile, signal) for e in merged[:take]])
    return out
