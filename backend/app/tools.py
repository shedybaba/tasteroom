"""The tools both the agent and the fallback pipeline use: same functions, so the pipeline is
exactly "the agent with the decisions fixed". Every call is timed and recorded as a TraceStep."""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .filters import HIDDEN_RE, decide_hidden_gems, venue_filters
from .models import PlanOptions, PlanRequest, Recommendation, ResolvedTaste, SlimEntity, TraceStep
from .profile import Profile, build_profile
from .qloo_client import QlooClient
from .recommend import HIDDEN_GEMS_MAX, SIGNAL_TYPES, find_venue_tag, recommend, recommend_venues
from .resolve import resolve_city, resolve_members
from .filters import venue_kind_from_goal

log = logging.getLogger("tasteroom.tools")

MAX_LIST = 10  # names returned to the LLM per tool call


class PlanError(Exception):
    """User-facing failure (e.g. none of the tastes could be matched)."""


class NotAffected(Exception):
    """A refine-mode tool call for a domain the organizer's request does not touch (refused, not traced)."""


@dataclass
class RefineState:
    """Present only while refining an existing plan."""
    instruction: str
    allowed: set[str] | None                   # domains the request may touch; None = the agent decides
    current_price: int | None = None           # price ceiling the plan currently uses (to make "cheaper" cheaper)
    current_hoods: set[str] = field(default_factory=set)       # neighbourhoods of the current top venues
    primary_hood: str | None = None                            # neighbourhood of the headline (first) venue
    current_addresses: list[str] = field(default_factory=list)  # fallback when saved venues lack a neighbourhood
    touched: set[str] = field(default_factory=set)
    notes: dict[str, list[str]] = field(default_factory=dict)   # domain -> what was applied ("hidden gems on", ...)

    def note(self, domain: str, text: str) -> None:
        self.touched.add(domain)
        if text not in self.notes.setdefault(domain, []):
            self.notes[domain].append(text)


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
    refine: RefineState | None = None
    known_tags: dict[str, str] = field(default_factory=dict)                       # tag id -> name, from find_tags
    neighbourhoods: dict[str, tuple[str, str, int]] = field(default_factory=dict)  # lower name -> (name, id, venue count)

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)


def _brief(recs: list[Recommendation]) -> list[dict]:
    return [{"id": r.entity.id, "name": r.entity.name} for r in recs[:MAX_LIST]]


async def _ensure_profile(ctx: PlanContext) -> Profile:
    if ctx.profile is None:
        ctx.resolved = await resolve_members(ctx.client, ctx.request.members)
        ctx.profile = build_profile(ctx.resolved)
        failed = [r.input for r in ctx.resolved if r.lookup_failed]
        missed = [r.input for r in ctx.resolved if r.entity is None and not r.lookup_failed]
        if missed:
            ctx.warn(f"Could not match {len(missed)} taste(s) in Qloo: {', '.join(missed[:8])}")
        if failed:  # Qloo busy/erroring: not the organizer's spelling, so say so
            ctx.warn(f"Qloo was busy, so {len(failed)} taste(s) were not looked up ({', '.join(failed[:6])}). "
                     "Building the plan again usually fixes this.")
    if not ctx.profile.entities:
        raise PlanError("None of the tastes could be matched to Qloo entities. Check spelling or pick a type.")
    return ctx.profile


async def tool_resolve_tastes(ctx: PlanContext, **_: Any) -> tuple[dict, str]:
    profile = await _ensure_profile(ctx)
    missed = [r.input for r in ctx.resolved if r.entity is None]
    shared = [pe.display or pe.entity.name for pe in profile.entities.values() if pe.weight > 1]
    out = {
        "matched": len(ctx.resolved) - len(missed), "unmatched": missed[:10],
        "entities": [pe.display or pe.entity.name for pe in profile.entities.values()][:15], "named_by_several_members": shared[:10],
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


def _guard(ctx: PlanContext, domain: str) -> None:
    r = ctx.refine
    if r and r.allowed is not None and domain not in r.allowed:
        raise NotAffected(f"{domain} is not affected by this request. Only re-query: {', '.join(sorted(r.allowed))}.")


def _gems(ctx: PlanContext, agent_value: bool | None) -> tuple[bool, list[str], list[str]]:
    """(apply, inferred-from-goal, from-refinement). The form and the goal work as in a normal run; while refining,
    the organizer's request counts too (and is labelled as coming from the refinement)."""
    gems, source = decide_hidden_gems(ctx.request.event_goal, ctx.request.options, agent_value)
    if gems:
        return True, (["hidden_gems"] if source == "goal" else []), []
    if ctx.refine and HIDDEN_RE.search(ctx.refine.instruction):
        return True, [], ["hidden_gems"]
    return False, [], []


async def tool_recommend(ctx: PlanContext, domain: str, hidden_gems: bool | None = None,
                         content_type: str | None = None, tags: list[str] | None = None, **_: Any) -> tuple[dict, str]:
    if domain not in ("music", "brands", "content"):
        raise ValueError("domain must be music, brands or content (use find_venues for venues)")
    _guard(ctx, domain)
    profile = await _ensure_profile(ctx)
    opts = ctx.request.options.model_copy()
    gems, inferred, refined = _gems(ctx, hidden_gems)
    opts.hidden_gems = gems
    ctype = content_type if domain == "content" and content_type in ("podcast", "tv_show") else None
    # Tags must be ones find_tags returned in this run (ids or names); anything else is dropped.
    by_name = {n.lower(): i for i, n in ctx.known_tags.items()}
    tag_ids = list(dict.fromkeys(t if t in ctx.known_tags else by_name.get(str(t).lower(), "") for t in (tags or [])))
    tag_ids = [t for t in tag_ids if t]
    res = await recommend(ctx.client, domain, profile, options=opts, content_type=ctype, tags=tag_ids or None)
    ctx.results[domain] = res.recommendations
    for w in res.warnings:
        ctx.warn(w)
    tag_names = list(dict.fromkeys(ctx.known_tags[t] for t in res.used_tags))  # two taxonomies can both call a tag "Chill"
    shown: dict[str, Any] = {"domain": domain, **({"content_type": ctype} if ctype else {})}
    if gems:
        shown |= {"hidden_gems": True, "filter.popularity.max": HIDDEN_GEMS_MAX[domain]}
    if tag_names:
        shown["tags"] = ", ".join(tag_names)
        refined.append("tags")
    if ctx.refine:
        ctx.refine.touched.add(domain)
        if gems:
            ctx.refine.note(domain, "hidden gems on")
        for name in tag_names:
            ctx.refine.note(domain, f"tag: {name}")
    ignored = bool(hidden_gems) and not gems
    return ({"domain": domain, "count": len(res.recommendations), "picks": _brief(res.recommendations),
             **({"note": "hidden_gems ignored: the organizer did not ask for it"} if ignored else {}),
             "_trace": {"args": shown, "inferred": inferred, "refined": refined}},
            f"{len(res.recommendations)} {domain} picks" + (" (hidden gems)" if gems else "") + (f" ({', '.join(tag_names)})" if tag_names else ""))


async def _neighbourhood_location(ctx: PlanContext, name: str) -> tuple[str, str]:
    known = ctx.neighbourhoods.get(name.strip().lower())
    if known:
        return known[0], known[1]
    found = await resolve_city(ctx.client, name.strip())
    if found is None:
        raise ValueError(f"Could not find a neighbourhood called '{name}'. Call list_neighbourhoods and use one of those names.")
    return found.name, found.id


async def tool_find_venues(ctx: PlanContext, **agent_args: Any) -> tuple[dict, str]:
    _guard(ctx, "venues")
    profile = await _ensure_profile(ctx)
    if not ctx.city_done:
        await tool_resolve_city(ctx)
    goal, refined = ctx.request.event_goal, []
    # Only filters the organizer set (form) or the goal states/implies are applied; see filters.py.
    # While refining, the organizer's request counts as stated too.
    applied = venue_filters(goal, ctx.request.options, agent_args)
    if ctx.refine:
        base = venue_filters(goal, ctx.request.options, {})
        applied = venue_filters(f"{goal} {ctx.refine.instruction}", ctx.request.options, agent_args)
        refined = [k for k, v in applied.args.items() if base.args.get(k) != v]
        applied.inferred = [k for k in applied.inferred if k not in refined]
        if "price_level_max" in refined:  # "cheaper" means cheaper than what the plan uses now
            cur = ctx.refine.current_price
            applied.args["price_level_max"] = max(1, min(3, cur - 1 if cur else 2))
    a = dict(applied.args)
    location_id, hood = None, None
    if agent_args.get("neighbourhood") and ctx.refine:
        hood, location_id = await _neighbourhood_location(ctx, str(agent_args["neighbourhood"]))
        a["neighbourhood"] = hood
        refined.append("neighbourhood")
    opts = ctx.request.options.model_copy(update={
        "venue_kind": a.get("venue_kind"), "price_level_max": a.get("price_level_max"),
        "day": a.get("day"), "hidden_gems": bool(a.get("hidden_gems"))})
    res = await recommend_venues(ctx.client, profile, locality=ctx.locality, city=ctx.request.city, options=opts,
                                 location_id=location_id)
    ctx.results["venues"] = res.recommendations
    for w in res.warnings:
        ctx.warn(w)
    if a.get("hidden_gems"):
        a["filter.popularity.max"] = HIDDEN_GEMS_MAX["venues"]
    if ctx.refine:
        ctx.refine.touched.add("venues")
        if "price_level_max" in refined:
            ctx.refine.note("venues", f"price <= {a['price_level_max']}")
        if hood:
            ctx.refine.note("venues", f"area: {hood}")
        if a.get("hidden_gems") and "hidden_gems" in refined:
            ctx.refine.note("venues", "hidden gems on")
    bits = [b for b in (opts.venue_kind, f"price<={opts.price_level_max}" if opts.price_level_max else None, opts.day, hood) if b]
    return ({"domain": "venues", "count": len(res.recommendations), "picks": _brief(res.recommendations),
             **({"note": "ignored " + ", ".join(applied.ignored) + ": the organizer did not state them"} if applied.ignored else {}),
             "_trace": {"args": a, "inferred": applied.inferred, "refined": refined}},
            f"{len(res.recommendations)} venues" + (f" ({', '.join(bits)})" if bits else ""))


# Tag taxonomies worth trying first for each domain (measured: the plain genre tag is sometimes empty).
TAG_PARENT_TYPES = {"music": {"urn:entity:artist"}, "brands": {"urn:entity:brand"}, "venues": {"urn:entity:place"},
                    "content": {"urn:entity:podcast", "urn:entity:tv_show"}}
TAG_PREFERENCE = ["urn:tag:style:qloo", "urn:tag:music:qloo", "urn:tag:genre:music", "urn:tag:genre:media", "urn:tag:genre:place"]


async def tool_find_tags(ctx: PlanContext, domain: str, query: str, **_: Any) -> tuple[dict, str]:
    """Look up Qloo tags (moods, styles, genres) for a domain, so a request like "more chill" can become a filter."""
    if domain not in TAG_PARENT_TYPES:
        raise ValueError("domain must be music, brands, content or venues")
    _guard(ctx, domain)
    found = [t for t in await ctx.client.find_tags(str(query).strip()[:40], take=20)
             if any(p.get("type") in TAG_PARENT_TYPES[domain] for p in t.get("parents", []))]
    rank = lambda t: next((i for i, pre in enumerate(TAG_PREFERENCE) if str(t.get("id", "")).startswith(pre)), len(TAG_PREFERENCE))  # noqa: E731
    top = sorted(found, key=rank)[:6]
    for t in top:
        ctx.known_tags[t["id"]] = t.get("name") or t["id"]
    return ({"domain": domain, "tags": [{"id": t["id"], "name": t.get("name")} for t in top]},
            f"{len(top)} tags for '{str(query).strip()[:40]}'")


async def tool_list_neighbourhoods(ctx: PlanContext, **_: Any) -> tuple[dict, str]:
    """Neighbourhoods where this community's best venues are, so "a different neighbourhood" can name one."""
    _guard(ctx, "venues")
    profile = await _ensure_profile(ctx)
    if not ctx.city_done:
        await tool_resolve_city(ctx)
    if ctx.locality is None:
        raise ValueError("The city is not a Qloo locality, so neighbourhoods are unavailable.")
    params: dict[str, Any] = {"filter.type": "urn:entity:place", "filter.location": ctx.locality.id, "take": 50,
                              "signal.interests.entities": profile.ids(types=SIGNAL_TYPES["venues"])}
    kind = ctx.request.options.venue_kind or venue_kind_from_goal(ctx.request.event_goal)
    if kind and (tag := await find_venue_tag(ctx.client, kind)):
        params["filter.tags"] = tag
    venues = (await ctx.client.insights(params)).entities
    counts: dict[str, tuple[str, str, int]] = {}
    for v in venues:
        if v.neighborhood and v.neighborhood_id:
            n, i, c = counts.get(v.neighborhood.lower(), (v.neighborhood, v.neighborhood_id, 0))
            counts[v.neighborhood.lower()] = (n, i, c + 1)
    ctx.neighbourhoods = counts
    cur = ctx.refine.current_hoods if ctx.refine else set()
    addrs = " | ".join(ctx.refine.current_addresses).lower() if ctx.refine else ""
    primary = ctx.refine.primary_hood if ctx.refine else None
    rows = [{"name": n, "venues": c, "current": n in cur or (not cur and n.lower() in addrs), "headline_pick_is_here": n == primary}
            for n, _i, c in sorted(counts.values(), key=lambda t: -t[2])[:8]]
    return {"neighbourhoods": rows}, f"{len(rows)} neighbourhoods with matching venues"


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
    "find_tags": tool_find_tags, "list_neighbourhoods": tool_list_neighbourhoods,  # used when refining
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
         "hidden_gems": {"type": "boolean", "description": "Only if the organizer asked for less mainstream picks."},
         "content_type": {"type": "string", "enum": ["podcast", "tv_show"], "description": "content only; omit for both."}},
         "required": ["domain"], "additionalProperties": False}},
    {"type": "function", "name": "find_venues",
     "description": "Get Qloo venue recommendations in the event city. Leave every argument out unless the organizer stated it: the system applies only filters the organizer set or the event goal implies.",
     "parameters": {"type": "object", "properties": {
         "venue_kind": {"type": "string", "description": "only if the organizer named a kind of place, e.g. bar, cafe, park"},
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


def _refine_schemas() -> list[dict]:
    """Tools offered while refining: the normal ones plus tag lookup and neighbourhoods, with tags / neighbourhood args."""
    out = []
    for t in TOOL_SCHEMAS:
        if t["name"] in ("resolve_tastes", "resolve_city", "explain"):
            continue  # profile and city are known; explanations come with each recommendation
        t = json.loads(json.dumps(t))
        if t["name"] == "recommend":
            t["description"] += " Pass tags (ids or names from find_tags) to steer the vibe."
            t["parameters"]["properties"]["tags"] = {"type": "array", "items": {"type": "string"},
                                                       "description": "Tag ids or names returned by find_tags in this run."}
        if t["name"] == "find_venues":
            t["parameters"]["properties"]["neighbourhood"] = {"type": "string", "description": "A name from list_neighbourhoods."}
        out.append(t)
    out += [
        {"type": "function", "name": "find_tags",
         "description": "Look up Qloo tags (moods, styles, genres) for a domain, e.g. 'chill' for music. Use them with recommend(tags=...).",
         "parameters": {"type": "object", "properties": {
             "domain": {"type": "string", "enum": ["music", "brands", "content", "venues"]}, "query": {"type": "string"}},
             "required": ["domain", "query"], "additionalProperties": False}},
        {"type": "function", "name": "list_neighbourhoods",
         "description": "List neighbourhoods of the event city where this community's best venues are (marks the ones the current plan already uses).",
         "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    ]
    return out


REFINE_TOOL_SCHEMAS = _refine_schemas()


def _fmt_args(args: dict) -> dict:
    return {k: v for k, v in args.items() if v not in (None, "", False)}


async def execute(ctx: PlanContext, name: str, args: dict[str, Any]) -> dict:
    """Run one tool, record a TraceStep, and return a JSON-able result for the LLM. Never raises
    (except PlanError, which must reach the user)."""
    t0 = time.perf_counter()
    ok, summary, out = True, "", {}
    shown, inferred, refined = _fmt_args(args), [], []
    try:
        if name not in TOOLS:
            raise ValueError(f"unknown tool {name}")
        out, summary = await TOOLS[name](ctx, **args)
        trace_info = out.pop("_trace", None)  # tools report the args they actually applied
        if trace_info:
            shown, inferred, refined = trace_info["args"], trace_info["inferred"], trace_info.get("refined", [])
    except PlanError:
        raise
    except NotAffected as exc:  # refused before doing anything: tell the model, but keep it out of the trace
        return {"error": str(exc)}
    except Exception as exc:  # tool failures are reported to the model and shown in the trace
        ok, summary, out = False, f"{type(exc).__name__}: {str(exc)[:120]}", {"error": str(exc)[:200]}
        log.warning("tool %s failed: %s", name, exc)
    if ctx.refine and ok and name in ("explain", "finish"):  # bookkeeping, not work: a refinement's trace shows only real re-queries
        return out
    ctx.trace.append(TraceStep(step=len(ctx.trace) + 1, tool=name, args=shown, inferred=inferred, refined=refined, summary=summary,
                               ms=int((time.perf_counter() - t0) * 1000), ok=ok))
    return out
