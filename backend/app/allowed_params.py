"""Per-filter.type whitelist for /v2/insights.

Qloo silently ignores unknown or unsupported parameters (200 with unchanged results), so a typo
looks like it worked. Everything goes through clean_params(), which drops and warns on anything
not listed here. Source: the Entity Type Parameter Guide, updated with live findings
(see API_FINDINGS.md).
"""
import logging
from typing import Any

log = logging.getLogger("tasteroom.params")

ARTIST = "urn:entity:artist"
BRAND = "urn:entity:brand"
PLACE = "urn:entity:place"
PODCAST = "urn:entity:podcast"
TV_SHOW = "urn:entity:tv_show"
SUPPORTED_TYPES = {
    ARTIST, BRAND, PLACE, PODCAST, TV_SHOW,
    "urn:entity:book", "urn:entity:destination", "urn:entity:movie",
    "urn:entity:person", "urn:entity:video_game",
}

COMMON = {
    "filter.type", "bias.trends", "filter.exclude.entities", "filter.exclude.tags",
    "operator.exclude.tags", "filter.external.exists", "operator.filter.external.exists",
    "filter.parents.types", "filter.popularity.min", "filter.popularity.max",
    "filter.results.entities", "filter.results.entities.query", "filter.tags",
    "operator.filter.tags", "signal.interests.entities", "signal.interests.tags",
    "signal.demographics.age", "signal.demographics.gender", "signal.demographics.audiences",
    "signal.demographics.audiences.weight", "offset", "take", "page",
    # Verified live: native per-input-entity explanation (query.explainability).
    "feature.explainability",
    # Verified live: ONE positive number or label (very_low..very_high) for the whole signal group.
    # A per-entity list ("10,1,1") is a 400, so per-member weighting is done client-side.
    "signal.interests.entities.weight",
}

PLACE_ONLY = {
    "bias.quality", "sort_by", "filter.address", "filter.hours", "filter.geocode.name",
    "filter.geocode.admin1_region", "filter.geocode.admin2_region",
    "filter.geocode.country_code", "filter.location", "filter.location.radius",
    "filter.location.geohash", "filter.exclude.location.geohash", "filter.price_level.min",
    "filter.price_level.max", "filter.price_range.from", "filter.price_range.to",
    "filter.properties.business_rating.min", "filter.properties.business_rating.max",
    "filter.external.tripadvisor.rating.min", "filter.external.tripadvisor.rating.max",
    "filter.external.tripadvisor.rating.count.min", "filter.external.tripadvisor.rating.count.max",
    "filter.references_brand",
    # Verified live: city name as free text ("Austin, Texas"). The locality-ID route is preferred.
    "filter.location.query",
}

TV_ONLY = {
    "filter.rating.min", "filter.rating.max", "filter.content_rating",
    "filter.release_year.min", "filter.release_year.max",
    "filter.finale_year.min", "filter.finale_year.max",
}

# Documented somewhere but not in the matrix. Only passed through when test_mode=True,
# until the smoke test proves them (then move them into the sets above).
# Proven NOT to work (silently ignored): filter.price_range.min/max (use .from/.to or price_level),
# filter.exists / filter.external.exists (no observable effect; every result already had an image).
UNVERIFIED = {
    "signal.interests.tags.weight", "signal.location.query", "operator.filter.exclude.tags",
    "filter.exists",
}

ALLOWED: dict[str, set[str]] = {
    ARTIST: COMMON, BRAND: COMMON, PODCAST: COMMON,
    TV_SHOW: COMMON | TV_ONLY,
    PLACE: COMMON | PLACE_ONLY,
    "urn:entity:destination": COMMON | PLACE_ONLY,
    "urn:entity:book": COMMON, "urn:entity:movie": COMMON | TV_ONLY,
    "urn:entity:person": COMMON, "urn:entity:video_game": COMMON,
}


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ",".join(_fmt(v) for v in value)
    return str(value)


def clean_params(params: dict[str, Any], test_mode: bool = False) -> tuple[dict[str, str], list[str]]:
    """Return (params safe to send as strings, names that were dropped). None values are skipped."""
    ftype = params.get("filter.type")
    if ftype not in SUPPORTED_TYPES:
        raise ValueError(f"unsupported or missing filter.type: {ftype!r}")
    allowed = ALLOWED[ftype] | (UNVERIFIED if test_mode else set())
    cleaned: dict[str, str] = {}
    dropped: list[str] = []
    for key, value in params.items():
        if value is None:
            continue
        if key not in allowed:
            dropped.append(key)
            continue
        cleaned[key] = _fmt(value)
    if dropped:
        log.warning("dropped params not valid for %s: %s", ftype, dropped)
    return cleaned, dropped
