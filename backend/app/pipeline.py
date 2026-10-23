"""Deterministic fallback: the same tools in a fixed order. Fills only what is still missing, so a
half-finished agent run keeps its work."""
from .filters import sponsors_decision
from .tools import PlanContext, execute


async def run_pipeline(ctx: PlanContext) -> None:
    """resolve -> city -> music -> venues -> brands -> content -> explain all."""
    if ctx.profile is None:
        await execute(ctx, "resolve_tastes", {})
    if not ctx.city_done and ctx.request.city.strip():
        await execute(ctx, "resolve_city", {})
    if "music" not in ctx.results:
        await execute(ctx, "recommend", {"domain": "music"})
    if "venues" not in ctx.results and ctx.request.city.strip():
        await execute(ctx, "find_venues", {})  # the tool derives filters from the form and the goal
    for domain in ("brands", "content"):
        if domain == "brands" and not sponsors_decision(ctx.request, ctx.resolved)[0]:
            continue   # no brand named, or a personal event: no sponsors at all
        if domain not in ctx.results:
            await execute(ctx, "recommend", {"domain": domain})
    for domain in ctx.results:
        if domain not in ctx.explained:
            await execute(ctx, "explain", {"domain": domain})
