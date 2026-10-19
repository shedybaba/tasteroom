"""The tools both the agent and the fallback pipeline use: same functions, so the pipeline is
exactly "the agent with the decisions fixed". Every call is timed and recorded as a TraceStep."""
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .explain import explain  # noqa: F401  (explanations are built inside recommend; see tool_explain)
from .models import PlanOptions, PlanRequest, Recommendation, ResolvedTaste, SlimEntity, TraceStep
from .profile import Profile, build_profile
from .qloo_client import QlooClient
from .recommend import recommend, recommend_venues
from .resolve import resolve_city, resolve_members

log = logging.getLogger("tasteroom.tools")

MAX_LIST = 10  # names returned to the LLM per tool call


class PlanError(Exception):
    """User-facing failure (e.g. none of the tastes could be matched)."""


@dataclass
class PlanContext:
    request: PlanRequest
    client: QlooClient
    resolved: list[ResolvedTaste] = field(default_factory=list)
    profile: Profile | None = None
    locality: SlimEntity | None = None
    city_done: bool = False
    results: dict[str, list[Recommendation]] = field(default_factory=dict)  # a key = domain was attempted
    explained: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)


def _brief(recs: list[Recommendation]) -> list[dict]:
    return [{"id": r.entity.id, "name": r.entity.name} for r in recs[:MAX_LIST]]


async def _ensure_profile(ctx: PlanContext) -> Profile:
    if ctx.profile is None:
        ctx.resolved = await resolve_members(ctx.client, ctx.request.members)
        ctx.profile = build_profile(ctx.resolved)
        missed = [r.input for r in ctx.resolved if r.entity is None]
        if missed:
            ctx.warn(f"Could not match {len(missed)} taste(s) in Qloo: {', '.join(missed[:8])}")
    if not ctx.profile.entities:
        raise PlanError("None of the tastes could be matched to Qloo entities. Check spelling or pick a type.")
    return ctx.profile


async def tool_resolve_tastes(ctx: PlanContext, **_: Any) -> tuple[dict, str]:
    profile = await _ensure_profile(ctx)
    missed = [r.input for r in ctx.resolved if r.entity is None]
    shared = [pe.entity.name for pe in profile.entities.values() if pe.weight > 1]
    out = {
        "matched": len(ctx.resolved) - len(missed), "unmatched": missed[:10],
        "entities": [pe.entity.name for pe in profile.entities.values()][:15], "named_by_several_members": shared[:10],
    }
    return out, f"{out['matched']}/{len(ctx.resolved)} tastes matched; {len(shared)} shared by several members"


async def tool_resolve_city(ctx: PlanContext, city: str | None = None, **_: Any) -> tuple[dict, str]:
    name = (city or ctx.request.city).strip()
    ctx.locality = await resolve_city(ctx.client, name)
    ctx.city_done = True
    if ctx.locality is None:
        ctx.warn(f"Could not resolve '{name}' to a Qloo locality; venues use the city name instead.")
    return ({"found": ctx.locality is not None, "name": ctx.locality.name if ctx.locality else None},
            f"locality: {ctx.locality.name}" if ctx.locality else f"'{name}' not found as a locality")


async def tool_recommend(ctx: PlanContext, domain: str, hidden_gems: bool | None = None,
                         content_type: str | None = None, **_: Any) -> tuple[dict, str]:
    if domain not in ("music", "brands", "content"):
        raise ValueError("domain must be music, brands or content (use find_venues for venues)")
    profile = await _ensure_profile(ctx)
    opts = ctx.request.options.model_copy()
    if hidden_gems is not None:
        opts.hidden_gems = hidden_gems
    res = await recommend(ctx.client, domain, profile, options=opts,
                          content_type=content_type if content_type in ("podcast", "tv_show") else None)
    ctx.results[domain] = res.recommendations
    for w in res.warnings:
        ctx.warn(w)
    return ({"domain": domain, "count": len(res.recommendations), "picks": _brief(res.recommendations)},
            f"{len(res.recommendations)} {domain} picks" + (" (hidden gems)" if opts.hidden_gems else ""))


async def tool_find_venues(ctx: PlanContext, venue_kind: str | None = None, price_level_max: int | None = None,
                           day: str | None = None, hidden_gems: bool | None = None, **_: Any) -> tuple[dict, str]:
    profile = await _ensure_profile(ctx)
    if not ctx.city_done:
        await tool_resolve_city(ctx)
    opts = ctx.request.options.model_copy()
    # Explicit tool args win; otherwise keep what the organizer set in the form.
    if venue_kind:
        opts.venue_kind = venue_kind
    if price_level_max:
        opts.price_level_max = price_level_max
    if day:
        opts.day = day
    if hidden_gems is not None:
        opts.hidden_gems = hidden_gems
    res = await recommend_venues(ctx.client, profile, locality=ctx.locality, city=ctx.request.city, options=opts)
    ctx.results["venues"] = res.recommendations
    for w in res.warnings:
        ctx.warn(w)
    bits = [b for b in (opts.venue_kind, f"price<={opts.price_level_max}" if opts.price_level_max else None, opts.day) if b]
    return ({"domain": "venues", "count": len(res.recommendations), "picks": _brief(res.recommendations)},
            f"{len(res.recommendations)} venues" + (f" ({', '.join(bits)})" if bits else ""))


async def tool_explain(ctx: PlanContext, domain: str, **_: Any) -> tuple[dict, str]:
    """Explanations are computed from Qloo's explainability data while recommending; this tool surfaces
    them (top contributors + shared tags) so the agent can ground its notes in them."""
    recs = ctx.results.get(domain)
    if recs is None:
        raise ValueError(f"no {domain} results yet: call the recommend / find_venues tool first")
    ctx.explained.add(domain)
    rows = [{
        "name": r.entity.name,
        "top_members": [f"{c.member} ({c.score:.0%})" for c in r.why[:3]],
        "shared_tags": r.shared_tags[:4], "method": r.explanation_method,
    } for r in recs[:5]]
    return {"domain": domain, "explanations": rows}, f"explanations for {len(recs)} {domain} picks"


async def tool_finish(ctx: PlanContext, notes: str = "", **_: Any) -> tuple[dict, str]:
    return {"ok": True}, (notes or "done")[:160]


TOOLS = {
    "resolve_tastes": tool_resolve_tastes, "resolve_city": tool_resolve_city, "recommend": tool_recommend,
    "find_venues": tool_find_venues, "explain": tool_explain, "finish": tool_finish,
}

TOOL_SCHEMAS = [
    {"type": "function", "name": "resolve_tastes",
     "description": "Match every member's tastes to Qloo entities and build the community taste profile. Call first.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "resolve_city",
     "description": "Look up the event city as a Qloo locality (needed for venues).",
     "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "additionalProperties": False}},
    {"type": "function", "name": "recommend",
     "description": "Get Qloo recommendations for music (artists), brands (sponsors/merch partners) or content (podcasts/TV shows).",
     "parameters": {"type": "object", "properties": {
         "domain": {"type": "string", "enum": ["music", "brands", "content"]},
         "hidden_gems": {"type": "boolean", "description": "Prefer less mainstream picks."},
         "content_type": {"type": "string", "enum": ["podcast", "tv_show"], "description": "content only; omit for both."}},
         "required": ["domain"], "additionalProperties": False}},
    {"type": "function", "name": "find_venues",
     "description": "Get Qloo venue recommendations in the event city. Pick venue_kind to suit the event.",
     "parameters": {"type": "object", "properties": {
         "venue_kind": {"type": "string", "description": "e.g. bar, lounge, event venue, restaurant, cafe, park, nightclub"},
         "price_level_max": {"type": "integer", "minimum": 1, "maximum": 4, "description": "ONLY if a budget was stated"},
         "day": {"type": "string", "description": "weekday the event is on, ONLY if the organizer stated it, e.g. saturday"},
         "hidden_gems": {"type": "boolean"}}, "additionalProperties": False}},
    {"type": "function", "name": "explain",
     "description": "Show why the picks in a domain were recommended (member contributions, shared tags). Call for every domain you use.",
     "parameters": {"type": "object", "properties": {
         "domain": {"type": "string", "enum": ["music", "venues", "brands", "content"]}},
         "required": ["domain"], "additionalProperties": False}},
    {"type": "function", "name": "finish", "description": "End the run when you have gathered everything.",
     "parameters": {"type": "object", "properties": {"notes": {"type": "string"}}, "additionalProperties": False}},
]


def _fmt_args(args: dict) -> dict:
    return {k: v for k, v in args.items() if v not in (None, "")}


async def execute(ctx: PlanContext, name: str, args: dict[str, Any]) -> dict:
    """Run one tool, record a TraceStep, and return a JSON-able result for the LLM. Never raises
    (except PlanError, which must reach the user)."""
    t0 = time.perf_counter()
    ok, summary, out = True, "", {}
    try:
        if name not in TOOLS:
            raise ValueError(f"unknown tool {name}")
        out, summary = await TOOLS[name](ctx, **args)
    except PlanError:
        raise
    except Exception as exc:  # tool failures are reported to the model and shown in the trace
        ok, summary, out = False, f"{type(exc).__name__}: {str(exc)[:120]}", {"error": str(exc)[:200]}
        log.warning("tool %s failed: %s", name, exc)
    ctx.trace.append(TraceStep(step=len(ctx.trace) + 1, tool=name, args=_fmt_args(args), summary=summary,
                               ms=int((time.perf_counter() - t0) * 1000), ok=ok))
    return out
