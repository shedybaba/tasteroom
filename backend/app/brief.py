"""Event brief: the LLM writes and organises, but may only pick entities Qloo returned.
validate_brief() enforces that, and builds a templated brief when there is no LLM."""
import json
import logging
from collections import Counter

from .llm import LLM
from .models import Brief, BriefPick, Recommendation
from .tools import PlanContext

log = logging.getLogger("tasteroom.brief")

from .explain import NOISE_TAG_NAMES as NOISE_TAGS  # noqa: E402

# Brief field -> (recommendation domain, max picks)
SECTIONS = {"music": ("music", 4), "venue": ("venues", 3), "sponsors": ("brands", 3), "content": ("content", 3)}

BRIEF_INSTRUCTIONS = """You write event briefs for community organizers.
Rules:
- Use ONLY the recommendations provided, referring to each by its exact name and entity_id. Never mention any \
artist, venue, brand, show or podcast that is not in the data, in ANY field (concept, run_of_show and promo_line included).
- Each pick's reason must come from its data. Each pick has a `fit` field saying who it suits: only name specific \
members when `fit` says the pick "stands out for" them; if it says it suits the whole group about equally, say so \
instead of listing individual members. You may also cite its shared_tags. Do not invent facts about a venue, artist \
or brand beyond the description given.
- Fit the event goal. music: up to 4 picks. venue: 1 top pick plus 2 backups. sponsors: up to 3. content: up to 3. \
If a domain has no recommendations, return an empty list for it.
- run_of_show: 4-6 short, practical lines. vibe_words: 3-5 words. concept: 2-3 sentences. promo_line: one line a \
community manager could post on Discord or X."""


def _members_phrase(rec: Recommendation) -> str:
    """Natural-language 'why' built only from the explanation data."""
    n = len(rec.why)
    stand_out = [c for c in rec.why if n and c.score >= STAND_OUT / n]
    parts = []
    if stand_out and n > 1:
        c = stand_out[0]
        names = " and ".join(x.member for x in stand_out[:2])
        parts.append(f"stands out for {names} (via {', '.join(c.via[:2])})" if c.via else f"stands out for {names}")
    elif n:
        parts.append(f"suits all {n} members whose tastes fed this search")
    if rec.shared_tags:
        parts.append("shares " + ", ".join(rec.shared_tags[:3]) + " with the group's tastes")
    if not parts:
        return "Recommended by Qloo for this community's combined taste."
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."  # not str.capitalize(): it would lowercase member and tag names


def reason_from_why(rec: Recommendation) -> str:
    return _members_phrase(rec)


STAND_OUT = 1.15  # a member "stands out" at 1.15x an even share (same threshold as the UI)


def fit_phrase(rec: Recommendation) -> str:
    """Who a pick suits, stated no more strongly than the explanation data supports."""
    n = len(rec.why)
    stand = [c for c in rec.why if n > 1 and c.score >= STAND_OUT / n]
    if stand:
        via = f" (via {', '.join(stand[0].via[:2])})" if stand[0].via else ""
        return "stands out for " + " and ".join(c.member for c in stand[:3]) + via
    if n > 1:
        return f"suits the whole group about equally ({n} members)"
    return f"suits {rec.why[0].member}" if n == 1 else "no member-level data"


def brief_input(ctx: PlanContext) -> str:
    def rows(domain: str) -> list[dict]:
        out = []
        for r in ctx.results.get(domain, []):
            out.append({
                "entity_id": r.entity.id, "name": r.entity.name,
                "description": (r.entity.description or "")[:140],
                "fit": fit_phrase(r), "shared_tags": r.shared_tags[:4],
                "address": r.entity.address[:80] if r.entity.address else None,
            })
        return out

    req = ctx.request
    return json.dumps({
        "community": req.community_name, "city": req.city, "event_goal": req.event_goal,
        "recommendations": {d: rows(d) for d in ("music", "venues", "brands", "content")},
    })


def validate_brief(brief: Brief, results: dict[str, list[Recommendation]]) -> tuple[Brief, int]:
    """Drop picks that are not Qloo results for that section's domain; restore canonical names; fill
    empty sections from the top-ranked results. Returns (clean brief, number of picks dropped)."""
    dropped = 0
    data = brief.model_dump()
    for field, (domain, cap) in SECTIONS.items():
        allowed = {r.entity.id: r for r in results.get(domain, [])}
        keep: list[BriefPick] = []
        for pick in getattr(brief, field):
            eid = pick.entity_id.strip().upper()
            rec = allowed.get(eid)
            if rec is None:
                dropped += 1
                continue
            if any(k.entity_id == eid for k in keep):
                continue
            keep.append(BriefPick(entity_id=eid, name=rec.entity.name, reason=pick.reason.strip() or reason_from_why(rec)))
        if not keep and allowed:
            top = list(allowed.values())[0]
            keep = [BriefPick(entity_id=top.entity.id, name=top.entity.name, reason=reason_from_why(top))]
        data[field] = [p.model_dump() for p in keep[:cap]]
    if dropped:
        log.warning("brief validator dropped %d ungrounded pick(s)", dropped)
    return Brief(**data), dropped


def templated_brief(ctx: PlanContext) -> Brief:
    """No-LLM brief: every word about a pick comes from Qloo data."""
    req = ctx.request
    picks: dict[str, list[BriefPick]] = {}
    for field, (domain, cap) in SECTIONS.items():
        picks[field] = [BriefPick(entity_id=r.entity.id, name=r.entity.name, reason=reason_from_why(r))
                        for r in ctx.results.get(domain, [])[:cap]]
    # Vibe comes from music / content / venue tags; brand tags ("B2C") describe companies, not taste.
    tags = Counter(t for d in ("music", "content", "venues") for r in ctx.results.get(d, [])[:5]
                   for t in r.shared_tags if t.lower() not in NOISE_TAGS)
    vibe = [t for t, _ in tags.most_common(5)] or [t for r in (ctx.results.get("music") or [])[:3]
                                                     for t in r.entity.tags[:2] if t.lower() not in NOISE_TAGS][:4]
    goal = req.event_goal[0].upper() + req.event_goal[1:]
    concept = (f"{goal} in {req.city}, built from the tastes of {len(req.members)} members of {req.community_name}."
               + (f" The group's shared taste centres on {', '.join(v.lower() for v in vibe[:3])}." if vibe else ""))
    show = []
    if picks["venue"]:
        show.append(f"Doors open at {picks['venue'][0].name}")
    if picks["music"]:
        names = " and ".join(p.name for p in picks["music"][:2])
        show.append(f"Playlist built around {names}")
    if picks["sponsors"]:
        show.append(f"Partner moment with {picks['sponsors'][0].name}")
    if picks["content"]:
        show.append(f"Conversation starter: {picks['content'][0].name}")
    show += ["Members share their own picks", "Wrap-up and announce the next event"]
    return Brief(
        title=f"{req.community_name}: {req.event_goal}"[:90], concept=concept, vibe_words=(vibe or ["community"])[:5],
        run_of_show=show[:6], promo_line=f"{req.community_name} is hosting a {req.event_goal} in {req.city}. Be there!",
        **picks,
    )


async def write_brief(ctx: PlanContext, llm: LLM | None) -> tuple[Brief, int]:
    """Returns (validated brief, picks dropped). Falls back to the template on any LLM problem."""
    if llm is None:
        return templated_brief(ctx), 0
    try:
        raw = await llm.structured(instructions=BRIEF_INSTRUCTIONS, user=brief_input(ctx), schema=Brief, smart=True)
        return validate_brief(raw, ctx.results)
    except Exception as exc:
        log.warning("LLM brief failed (%s); using template", type(exc).__name__)
        ctx.warn("The AI brief writer was unavailable, so a templated brief was used. All picks are still from Qloo.")
        return templated_brief(ctx), 0
