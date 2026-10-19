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
HIDDEN_GEMS_MAX_POPULARITY = 0.7  # verified: mean popularity 0.82 -> 0.59


@dataclass
class DomainResult:
    domain: str
    recommendations: list[Recommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def find_venue_tag(client: QlooClient, kind: str) -> str | None:
    """Free text ("rooftop bar") -> a place tag id usable in filter.tags."""
    for tag in await client.find_tags(kind, take=10):
        if any(p.get("type") == PLACE for p in tag.get("parents", [])):
            return tag["id"]
    return None


def _base_params(ftype: str, signal_ids: list[str], options: PlanOptions, take: int,
                 audience_id: str | None) -> dict:
    params: dict = {
        "filter.type": ftype,
        "signal.interests.entities": signal_ids,
        "feature.explainability": True,
        "take": take,
    }
    if options.hidden_gems:
        params["filter.popularity.max"] = HIDDEN_GEMS_MAX_POPULARITY
    if audience_id:
        params["signal.demographics.audiences"] = audience_id
    return params


async def _query(client: QlooClient, params: dict) -> list[SlimEntity]:
    return (await client.insights(params)).entities


async def recommend_venues(
    client: QlooClient, profile: Profile, *, locality: SlimEntity | None, city: str,
    options: PlanOptions, take: int = DEFAULT_TAKE["venues"], audience_id: str | None = None,
) -> DomainResult:
    out = DomainResult("venues")
    signal = profile.ids(types=SIGNAL_TYPES["venues"])
    params = _base_params(PLACE, signal, options, take, audience_id)
    # A location filter is mandatory: without one Qloo infers location from taste (API_FINDINGS.md).
    if locality:
        params["filter.location"] = locality.id
    elif city.strip():
        params["filter.location.query"] = city.strip()
        out.warnings.append(f"Could not resolve '{city}' to a Qloo locality; searched by city name instead.")
    else:
        out.warnings.append("No city given: venues skipped.")
        return out
    if options.price_level_max:
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
    if not entities and locality and city.strip():
        out.warnings.append("Locality filter returned nothing; retried with the city name.")
        params.pop("filter.location")
        params["filter.location.query"] = city.strip()
        entities = await _query(client, params)
    if not entities:
        out.warnings.append("Qloo returned no venues for this city and filters.")
    out.recommendations = relative_to_list([explain(e, "venues", profile, signal) for e in entities])
    return out


async def recommend(
    client: QlooClient, domain: str, profile: Profile, *, options: PlanOptions | None = None,
    content_type: str | None = None, take: int | None = None, audience_id: str | None = None,
) -> DomainResult:
    """music / brands / content (venues use recommend_venues because of the location filter)."""
    options = options or PlanOptions()
    take = take or DEFAULT_TAKE[domain]
    out = DomainResult(domain)
    types = DOMAIN_TYPES[domain]
    if domain == "content" and content_type:
        types = [f"urn:entity:{content_type}"]
    signal = profile.ids(types=SIGNAL_TYPES[domain])
    batches = [
        await _query(client, _base_params(t, signal, options, take, audience_id)) for t in types
    ]
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
