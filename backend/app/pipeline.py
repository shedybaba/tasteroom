"""Deterministic fallback: the same tools in a fixed order. Fills only what is still missing, so a
half-finished agent run keeps its work."""
import re

from .tools import PlanContext, execute

VENUE_KIND_HINTS = [  # event goal keywords -> a Qloo venue tag search term
    (r"party|launch|club|night ?out|celebrat", "lounge"),
    (r"network|conference|workshop|demo|panel|summit", "event venue"),
    (r"chill|hang ?out|meetup|social|drinks|mixer", "bar"),
    (r"coffee|study|book|read|brunch", "cafe"),
    (r"run|hike|outdoor|picnic|walk|sport", "park"),
]


def infer_venue_kind(goal: str) -> str | None:
    for pattern, kind in VENUE_KIND_HINTS:
        if re.search(pattern, goal.lower()):
            return kind
    return None


async def run_pipeline(ctx: PlanContext) -> None:
    """resolve -> city -> music -> venues -> brands -> content -> explain all."""
    if ctx.profile is None:
        await execute(ctx, "resolve_tastes", {})
    if not ctx.city_done and ctx.request.city.strip():
        await execute(ctx, "resolve_city", {})
    if "music" not in ctx.results:
        await execute(ctx, "recommend", {"domain": "music"})
    if "venues" not in ctx.results and ctx.request.city.strip():
        kind = ctx.request.options.venue_kind or infer_venue_kind(ctx.request.event_goal)
        await execute(ctx, "find_venues", {"venue_kind": kind} if kind else {})
    for domain in ("brands", "content"):
        if domain not in ctx.results:
            await execute(ctx, "recommend", {"domain": domain})
    for domain in ctx.results:
        if domain not in ctx.explained:
            await execute(ctx, "explain", {"domain": domain})
