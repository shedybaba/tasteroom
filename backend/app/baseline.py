"""The same request answered by the LLM alone (no Qloo data), for the Compare tab, plus stats that
show what Qloo adds: explained picks, picks verifiable in Qloo, venues confirmed in the city."""
import json
import logging

from .llm import LLM
from .models import BaselineBrief, BaselinePick, Brief, CompareStats, PlanRequest, Recommendation
from .qloo_client import QlooClient, QlooError
from .resolve import _norm, similarity

log = logging.getLogger("tasteroom.baseline")

BASELINE_INSTRUCTIONS = """You are an event planner. Recommend an event plan for this community from your own \
knowledge only: music artists, venue(s) in the city, sponsor brands, and a podcast or show to feature. \
music: up to 4 picks. venue: 1 top pick plus 2 backups. sponsors: up to 3. content: up to 3. \
Give each pick a short reason. run_of_show: 4-6 short lines. vibe_words: 3-5. promo_line: one line for Discord or X."""

VERIFY_SIMILARITY = 0.85
SECTION_TYPES = {
    "music": ["urn:entity:artist"], "sponsors": ["urn:entity:brand"],
    "content": ["urn:entity:podcast", "urn:entity:tv_show"], "venue": ["urn:entity:place"],
}


def baseline_input(req: PlanRequest) -> str:
    return json.dumps({
        "community": req.community_name, "city": req.city, "event_goal": req.event_goal,
        "members": [{"name": m.name, "tastes": [t.text for t in m.tastes]} for m in req.members],
    })


def canned_baseline(req: PlanRequest) -> BaselineBrief:
    """Mock mode (no LLM key): typical generic answer, clearly not personalised."""
    p = lambda n, r: BaselinePick(name=n, reason=r)  # noqa: E731
    return BaselineBrief(
        title=f"{req.community_name}: {req.event_goal}", vibe_words=["fun", "social", "upbeat"],
        concept=f"A lively {req.event_goal} in {req.city} with popular music and a central venue.",
        run_of_show=["Arrival and welcome", "Music set", "Networking", "Closing remarks"],
        music=[p("Drake", "Broad appeal."), p("Beyoncé", "Crowd pleaser.")],
        venue=[p(f"A popular rooftop bar in {req.city}", "Central and lively.")],
        sponsors=[p("Coca-Cola", "Widely recognised."), p("Nike", "Popular with young adults.")],
        content=[p("The Joe Rogan Experience", "Well-known podcast.")],
        promo_line=f"Join {req.community_name} for a {req.event_goal} in {req.city}!",
    )


async def llm_baseline(req: PlanRequest, llm: LLM | None) -> tuple[BaselineBrief, str]:
    if llm is None:
        return canned_baseline(req), "mock"
    out = await llm.structured(instructions=BASELINE_INSTRUCTIONS, user=baseline_input(req), schema=BaselineBrief, smart=True)
    return out, "llm"


def _city_matches(city: str | None, wanted: list[str]) -> bool:
    c = _norm(city or "")
    return bool(c) and any(c == _norm(w) or c in _norm(w) or _norm(w) in c for w in wanted if w)


async def verify_baseline(client: QlooClient, brief: BaselineBrief, city: str, locality_name: str | None) -> CompareStats:
    """Look every baseline pick up in Qloo. A venue counts as in-city only if the Qloo place's own
    geocode city matches the request (/search cannot take a locality id as a location filter)."""
    verified = venues = venues_in_city = 0
    total = 0
    for section, types in SECTION_TYPES.items():
        for pick in getattr(brief, section):
            total += 1
            if section == "venue":
                venues += 1
            try:
                found = await client.search(pick.name, types, take=5)
            except QlooError:
                continue
            hit = next((e for e in sorted(found, key=lambda e: -similarity(pick.name, e.name))
                        if similarity(pick.name, e.name) >= VERIFY_SIMILARITY), None)
            if hit is None:
                continue
            verified += 1
            if section == "venue" and _city_matches(hit.city, [city, locality_name or ""]):
                venues_in_city += 1
    return CompareStats(picks=total, with_explanation=0, verified_in_qloo=verified, venues=venues, venues_in_city=venues_in_city)


def qloo_stats(brief: Brief, results: dict[str, list[Recommendation]]) -> CompareStats:
    """Qloo-grounded picks: verified by construction (the validator keeps only Qloo results); explained if
    the underlying result has contributor or shared-tag data; venues come from a location-filtered query."""
    index = {r.entity.id: r for recs in results.values() for r in recs}
    picks = [p for field in SECTION_TYPES for p in getattr(brief, field)]
    explained = sum(1 for p in picks if p.entity_id in index and (index[p.entity_id].why or index[p.entity_id].shared_tags))
    return CompareStats(picks=len(picks), with_explanation=explained, verified_in_qloo=sum(1 for p in picks if p.entity_id in index),
                        venues=len(brief.venue), venues_in_city=len(brief.venue))
