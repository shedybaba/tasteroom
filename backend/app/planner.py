"""Orchestration: agent (with deterministic fallback) -> grounded brief -> PlanResponse."""
import asyncio
import logging
import sqlite3

from . import cache, personal as personal_mod, plan_store
from .agent import run_agent
from .attribution import attribute
from .brief import write_brief
from .config import settings
from .llm import LLM
from .models import PlanRequest, PlanResponse
from .pipeline import run_pipeline
from .qloo_client import QlooClient
from .tools import PlanContext, PlanError

log = logging.getLogger("tasteroom.planner")
CACHE_VERSION = "v1"
PLAN_TTL = 7 * cache.DAY


def normalize(req: PlanRequest) -> dict:
    d = req.model_dump(mode="json")
    for k in ("community_name", "city", "event_goal"):
        d[k] = " ".join(d[k].lower().split())
    for m in d["members"]:
        m["name"] = " ".join(m["name"].split())
        for t in m["tastes"]:
            t["text"] = " ".join(t["text"].lower().split())
    return d


def plan_id_for(req: PlanRequest) -> str:
    return cache.make_key(CACHE_VERSION, normalize(req))[:12]


def is_complete(ctx: PlanContext) -> bool:
    """Agent output is usable if it found venues (when a city was given) and at least one other domain.
    (BUILD_PLAN asks for two others; one lets the agent drop domains that do not fit the event, e.g. a
    podcast meetup keeps content + venues, instead of the pipeline re-adding everything.)"""
    have = {d for d, recs in ctx.results.items() if recs}
    needs_venues = bool(ctx.request.city.strip())
    return ctx.profile is not None and (not needs_venues or "venues" in have) and len(have - {"venues"}) >= 1


async def make_plan(req: PlanRequest, client: QlooClient, llm: LLM | None) -> PlanResponse:
    ctx = PlanContext(request=req, client=client)
    agent_ok = False
    if llm is not None and not settings.agent_disabled:
        try:
            await run_agent(ctx, llm)
            agent_ok = is_complete(ctx)
            if not agent_ok:
                ctx.warn("The agent's plan was incomplete, so the standard pipeline filled in the rest.")
        except PlanError:
            raise
        except Exception as exc:
            log.warning("agent failed: %s: %s", type(exc).__name__, str(exc)[:200])
            ctx.warn("The AI agent hit a problem, so the standard pipeline ran instead.")
    if not agent_ok:
        await run_pipeline(ctx)
    if not any(ctx.results.values()):
        raise PlanError("Qloo returned no recommendations for this community. Try other tastes or a larger city.")

    # Personal picks (one Qloo query per member) don't depend on the brief, so they run alongside the brief writer.
    # Mock data answers every query the same way, so personal picks would mean nothing there.
    members = [m.name for m in req.members]
    personal = (asyncio.sleep(0, ([], [])) if client.mock
                else personal_mod.run(client, ctx.resolved, ctx.results, ctx.queries, members, trace=ctx.trace))
    (brief, dropped), (picks, skips) = await asyncio.gather(write_brief(ctx, llm), personal)
    brief = attribute(brief, picks, ctx.results)   # a personal pick the writer put in the lineup says who it was chosen for
    mode = "mock" if client.mock else ("agent" if agent_ok else "pipeline")
    return PlanResponse(
        plan_id=plan_id_for(req), request=req, resolved=ctx.resolved, locality=ctx.locality,
        recommendations=ctx.results, brief=brief, trace=ctx.trace, mode=mode,  # type: ignore[arg-type]
        warnings=ctx.warnings, dropped_picks=dropped, personal=picks, personal_skipped=skips,
    )


def cached_plan(plan_id: str) -> PlanResponse | None:
    """Disk cache first (fast), then the durable SQLite copy (survives redeploys)."""
    hit = cache.get(f"plan:{plan_id}")
    if hit:
        return PlanResponse.model_validate(hit)
    try:
        return plan_store.get_store().load(plan_id)
    except (OSError, sqlite3.Error) as exc:
        log.warning("plan store unavailable: %s", type(exc).__name__)
        return None


def store_plan(plan: PlanResponse) -> None:
    cache.put(f"plan:{plan.plan_id}", plan.model_dump(mode="json"), PLAN_TTL)
    try:
        plan_store.get_store().save(plan)
    except (OSError, sqlite3.Error) as exc:  # the cache copy still serves it; never fail a request over persistence
        log.warning("could not persist plan: %s", type(exc).__name__)
