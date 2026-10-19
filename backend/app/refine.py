"""Refine an existing plan: the organizer says what to change, the agent re-runs only what that affects.

Flow: classify the request (which domains can it touch?) -> rebuild the plan's context from the saved plan ->
let the agent call the same tools, restricted to those domains -> if it changed nothing, apply a deterministic
fallback -> revise only the touched sections of the brief (untouched sections are restored verbatim) -> save as a new
version whose parent is the plan that was refined."""
import json
import logging
import re
from dataclasses import dataclass, field

from . import cache, plan_store
from .agent import run_agent
from .brief import DOMAIN_FIELD, revise_brief
from .config import settings
from .filters import HIDDEN_RE
from .llm import LLM
from .models import Change, PlanResponse, Refinement
from .profile import build_profile
from .qloo_client import QlooClient
from .rooms import clean_text
from .tools import REFINE_TOOL_SCHEMAS, PlanContext, PlanError, RefineState, execute

log = logging.getLogger("tasteroom.refine")
DOMAIN_ORDER = ("music", "venues", "brands", "content")
MAX_REFINE_CALLS = 8
REFINE_BUDGET_SECONDS = 45

QUICK_REFINEMENTS = ["Cheaper venue", "More hidden gems", "Swap the music vibe: more chill",
                     "Add a watch-party content theme", "Different neighbourhood"]

MOOD_WORDS = (r"chill(?:er|ed)?|mellow|relax(?:ed|ing)?|calm(?:er)?|upbeat|energetic|energy|hype|acoustic|lo-?fi|romantic|"
              r"soulful|jazzy|danceable|dance|slow(?:er)?|quiet(?:er)?")
# (name, pattern, domains the request can touch). A request may match several; their domains are unioned.
INTENTS: list[tuple[str, re.Pattern[str], set[str]]] = [(n, re.compile(p, re.I), d) for n, p, d in [
    ("price", r"cheap|afford|budget|less expensive|lower[- ]pric|too (?:expensive|pricey)|pricey", {"venues"}),
    ("gems", HIDDEN_RE.pattern + r"|mainstream|obscure|lesser|undiscovered", {"music", "brands", "content"}),
    ("hood", r"neighbou?rhood|\barea\b|district|part of (?:town|the city)|somewhere else|different (?:location|part)", {"venues"}),
    ("content", r"watch[- ]?party|\bshows?\b|series|movies?|films?|podcasts?|screening|stream|content", {"content"}),
    ("mood", r"\b(?:" + MOOD_WORDS + r")\b|vibe|\bmood\b|genre|\bmusic\b|\bsongs?\b|\bartists?\b|\bdj\b", {"music"}),
    ("sponsors", r"sponsor|\bbrands?\b|partner|merch", {"brands"}),
    ("venue", r"venue|\bbar\b|lounge|caf[eé]|restaurant|\bspot\b|\bplace\b|rooftop|club|capacity|outdoor|indoor", {"venues"}),
]]
_MOOD_STEM = {"chiller": "chill", "chilled": "chill", "relaxing": "relaxed", "calmer": "calm", "slower": "slow",
              "quieter": "quiet", "lofi": "lo-fi", "energy": "energetic", "danceable": "dance"}


@dataclass
class Intent:
    names: list[str] = field(default_factory=list)
    domains: set[str] | None = None   # None = could not tell: the agent decides
    mood: str | None = None


def classify(instruction: str) -> Intent:
    names, domains = [], set()
    for name, pattern, doms in INTENTS:
        if pattern.search(instruction):
            names.append(name)
            domains |= doms
    m = re.search(r"\b(" + MOOD_WORDS + r")\b", instruction, re.I)
    mood = _MOOD_STEM.get(m.group(1).lower(), m.group(1).lower()) if m else None
    return Intent(names, domains or None, mood)


def refine_id(parent_id: str, instruction: str) -> str:
    """Deterministic: asking the same thing of the same plan returns the saved version instead of paying again."""
    return cache.make_key("refine", parent_id, " ".join(instruction.lower().split()))[:12]


SYSTEM = """You are refining an existing event plan. The organizer asked for ONE change. Use the tools to re-query ONLY \
the domains that change affects and leave every other domain exactly as it is (calls for unaffected domains are refused).
- cheaper / price: call find_venues (the price ceiling is set for you from the request).
- hidden gems / less mainstream: call recommend with hidden_gems=true for each affected domain.
- a different vibe or genre (chill, upbeat, acoustic...): find_tags for the domain with that word, then recommend with \
tags=[...] using tag ids or names from find_tags.
- a different neighbourhood: call list_neighbourhoods, then find_venues with neighbourhood=<a name NOT marked current; \
if every area is current, any area where headline_pick_is_here is false>.
- add a show, podcast or watch-party theme: recommend with domain=content.
Call independent tools together in one step. Never name a pick that a tool did not return, and do not write the brief \
(a separate step does). Call finish when done."""


def build_context(parent: PlanResponse, instruction: str, client: QlooClient, allowed: set[str] | None) -> PlanContext:
    price = next((s.args.get("price_level_max") for s in reversed(parent.trace) if s.tool == "find_venues"), None)
    venues = parent.recommendations.get("venues") or []
    state = RefineState(
        instruction=instruction, allowed=allowed, current_price=price if isinstance(price, int) else None,
        current_hoods={v.entity.neighborhood for v in venues[:3] if v.entity.neighborhood},
        primary_hood=venues[0].entity.neighborhood if venues else None,
        current_addresses=[v.entity.address for v in venues[:3] if v.entity.address])
    return PlanContext(
        request=parent.request, client=client, resolved=list(parent.resolved), profile=build_profile(parent.resolved),
        locality=parent.locality, city_done=True, results={d: list(r) for d, r in parent.recommendations.items()},
        explained=set(parent.recommendations), trace=[s.model_copy() for s in parent.trace], refine=state,
        # keep warnings about the tastes; query-specific ones belong to queries this refinement may re-run
        warnings=[w for w in parent.warnings if w.startswith(("Could not match", "Qloo was busy"))])


def user_message(parent: PlanResponse, instruction: str, allowed: set[str] | None, ctx: PlanContext) -> str:
    r = parent.request
    return json.dumps({
        "request": instruction, "event": {"community": r.community_name, "city": r.city, "goal": r.event_goal},
        "current_picks": {d: [x.entity.name for x in recs[:5]] for d, recs in parent.recommendations.items()},
        "domains_this_request_affects": sorted(allowed) if allowed else "you decide (re-query as few domains as possible)",
        "current_venue_neighbourhoods": sorted(ctx.refine.current_hoods) if ctx.refine else [],
        "current_price_ceiling": ctx.refine.current_price if ctx.refine else None,
    })


async def run_fallback(ctx: PlanContext, intent: Intent) -> None:
    """Deterministic version of the agent for requests it maps cleanly (and for when the LLM is unavailable)."""
    if intent.domains is None or ctx.refine is None:
        return
    names, allowed = set(intent.names), ctx.refine.allowed or set()
    if "hood" in names and "venues" in allowed:
        rows = (await execute(ctx, "list_neighbourhoods", {})).get("neighbourhoods", [])
        # prefer an area the plan does not use yet; if the top venues already span them all, at least leave the headline pick's area
        pick = next((x for x in rows if not x["current"]), None) or next((x for x in rows if not x["headline_pick_is_here"]), None)
        if pick:
            await execute(ctx, "find_venues", {"neighbourhood": pick["name"]})
    elif ({"price", "venue"} & names) and "venues" in allowed:
        await execute(ctx, "find_venues", {})
    if "gems" in names:
        for d in ("music", "brands", "content"):
            if d in allowed and d in ctx.results:
                await execute(ctx, "recommend", {"domain": d})
    if "mood" in names and intent.mood and "music" in allowed:
        tags = (await execute(ctx, "find_tags", {"domain": "music", "query": intent.mood})).get("tags", [])
        if tags:
            await execute(ctx, "recommend", {"domain": "music", "tags": [t["id"] for t in tags[:4]]})
    if "content" in names and "content" in allowed:
        await execute(ctx, "recommend", {"domain": "content"})


def _ids(recs, n=10) -> list[str]:
    return [r.entity.id for r in recs[:n]]


def compute_changes(previous, new, state: RefineState) -> list[Change]:
    out = []
    for d in DOMAIN_ORDER:
        if d not in state.touched:
            continue
        field_ = DOMAIN_FIELD[d]
        before = {p.entity_id for p in getattr(previous, field_)}
        picks = getattr(new, field_)
        out.append(Change(domain=d, swapped=sum(1 for p in picks if p.entity_id not in before), of=len(picks),
                          note=" · ".join(state.notes.get(d, [])) or None))
    return out


async def refine_plan(parent: PlanResponse, instruction: str, client: QlooClient, llm: LLM | None) -> PlanResponse:
    instruction = clean_text(instruction, 200)
    if len(instruction) < 3:
        raise PlanError("Tell the agent what to change, for example \"cheaper venue\".")
    intent = classify(instruction)
    allowed = intent.domains
    if allowed is not None and set(intent.names) <= {"gems"}:   # "more hidden gems" must not add a domain the plan lacks
        allowed = (allowed & set(parent.recommendations)) or allowed
    ctx = build_context(parent, instruction, client, allowed)
    state = ctx.refine
    assert state is not None

    mode = "pipeline"
    if llm is not None and not settings.agent_disabled:
        try:
            await run_agent(ctx, llm, system=SYSTEM, tools=REFINE_TOOL_SCHEMAS, user=user_message(parent, instruction, allowed, ctx),
                            max_calls=MAX_REFINE_CALLS, budget=REFINE_BUDGET_SECONDS)
            mode = "agent"
        except PlanError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("refine agent failed: %s: %s", type(exc).__name__, str(exc)[:160])
            ctx.warn("The AI agent hit a problem while refining, so the standard steps were used instead.")
    if not state.touched:
        mode = "pipeline"
        await run_fallback(ctx, intent)
    if not state.touched:
        raise PlanError("I couldn't turn that into a change. Try something like \"cheaper venue\", \"more hidden gems\", "
                        "\"more chill music\", \"add a watch-party content theme\" or \"different neighbourhood\".")
    if all(_ids(ctx.results[d]) == _ids(parent.recommendations.get(d, [])) for d in state.touched):
        raise PlanError("Nothing changed: Qloo returned the same picks for that request, so your current plan already fits it as well as the data allows.")

    brief, dropped = await revise_brief(ctx, llm, parent.brief, state.touched, instruction)
    root = parent.root_id or parent.plan_id
    version = max(plan_store.get_store().max_version(root), 1) + 1 if _store_ok() else parent.version + 1
    return PlanResponse(
        plan_id=refine_id(parent.plan_id, instruction), request=parent.request, resolved=parent.resolved,
        locality=parent.locality, recommendations=ctx.results, brief=brief, trace=ctx.trace,
        mode="mock" if client.mock else mode, warnings=ctx.warnings, dropped_picks=dropped,  # type: ignore[arg-type]
        parent_id=parent.plan_id, root_id=root, version=version,
        refinement=Refinement(instruction=instruction, trace_start=len(parent.trace), changes=compute_changes(parent.brief, brief, state)))


def _store_ok() -> bool:
    try:
        plan_store.get_store()
        return True
    except OSError:
        return False
