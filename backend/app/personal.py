"""Personal picks: for each member, a Qloo result found from THEIR tastes alone that also fits the group.

Why: the group query returns crowd-pleasers, and Qloo's per-member signal inside it is close to uniform, so most
members have no pick that stands out for them (see coverage.py). Asking Qloo "what would this one person like?" gives a
list that really is theirs. To keep it useful for an event, a personal pick must also fit the group:

1. one /v2/insights query per member per domain (music, content), seeded ONLY with that member's resolved entities;
2. take the highest-ranked result that
   - is not something a member already named (Qloo never returns the entities you seed with, so the group's own
     results can't contain them either; personal picks stay discoveries), and
   - fits the group: it is one of the group's results, OR Qloo's group-level affinity for it (filter.results.entities
     with the group signal) is within 5% of the average affinity of the group's results;
3. prefer a pick no other member already got, so the row doesn't show one artist eight times.
Nothing here is written by an LLM: the explanation is assembled from the data above."""
import asyncio
import logging
import time
from dataclasses import dataclass
from statistics import mean

from .models import PersonalPick, PersonalSkip, PlanOptions, Recommendation, ResolvedTaste, SlimEntity, TraceStep
from .profile import build_profile, short_type
from .qloo_client import QlooError
from .recommend import SIGNAL_TYPES, group_affinity, recommend

log = logging.getLogger("tasteroom.personal")

GROUP_FIT_RATIO = 0.95        # "close to the group average": within 5% of the group's average affinity
CANDIDATES_PER_MEMBER = 10    # how far down a member's own list we look for something that fits the group
MEMBER_TAKE = 20
CONCURRENCY = 4
PERSONAL_DOMAINS = ("music", "content")
LABEL = {"music": "music", "content": "shows and podcasts"}


@dataclass
class DomainQuery:
    """How the group's results for a domain were queried, so a member's query uses the same options (hidden gems, tags)."""
    options: PlanOptions
    content_type: str | None = None
    tags: list[str] | None = None


def fit_text(domain: str, fit: str, group_rank: int | None, ratio: float | None) -> str:
    if fit == "in_group_results" and group_rank:
        return f"it is #{group_rank} in the group's {LABEL[domain]} results"
    if ratio is not None and ratio >= 1:
        return "Qloo ties it to the group as strongly as the group's own average pick"
    return f"Qloo ties it to the group at {round((ratio or 0) * 100)}% of the group's average pull"


def explain_personal(member: str, domain: str, via: list[str], rank: int, fit: str, group_rank: int | None, ratio: float | None) -> str:
    own = f"{member}'s own tastes ({', '.join(via[:3])})" if via else f"{member}'s tastes on their own"
    return f"Qloo's #{rank} for {own}, and it fits the group too: {fit_text(domain, fit, group_rank, ratio)}."


def personal_recommendation(p: PersonalPick) -> Recommendation:
    """A personal pick as an ordinary Recommendation (one contributor), for code that expects results: the brief writer,
    the grounding validator and coverage. `why` has the one member, so it reads "suits <member>", never "suits everyone"."""
    from .models import Contribution
    return Recommendation(entity=p.entity, domain=p.domain, why=[Contribution(member=p.member, score=1.0, via=p.via)],
                          shared_tags=[], explanation_method="qloo_explainability")


async def _member_results(client, domain: str, resolved: list[ResolvedTaste], member: str, q: DomainQuery,
                          sem: asyncio.Semaphore) -> list[Recommendation] | str:
    mp = build_profile([r for r in resolved if r.member == member])
    if not any(short_type(pe.entity) in SIGNAL_TYPES[domain] for pe in mp.entities.values()):
        return "no_signal"
    async with sem:
        try:
            return (await recommend(client, domain, mp, options=q.options, content_type=q.content_type, take=MEMBER_TAKE, tags=q.tags)).recommendations
        except QlooError as exc:
            log.warning("personal query failed for %s/%s: status=%s", member, domain, exc.status)
            return "qloo_error"


async def _domain(client, domain: str, resolved: list[ResolvedTaste], group: list[Recommendation], q: DomainQuery,
                  members: list[str], sem: asyncio.Semaphore) -> tuple[list[PersonalPick], list[PersonalSkip]]:
    profile = build_profile(resolved)
    named = set(profile.entities)                               # everything any member already said
    group_rank = {r.entity.id: i + 1 for i, r in enumerate(group)}
    affs = [r.entity.affinity for r in group if r.entity.affinity is not None]
    average = mean(affs) if affs else None
    got = dict(zip(members, await asyncio.gather(*[_member_results(client, domain, resolved, m, q, sem) for m in members])))

    cands: dict[str, list[tuple[int, Recommendation]]] = {}
    for m, res in got.items():
        if isinstance(res, list):
            cands[m] = [(i + 1, r) for i, r in enumerate(x for x in res if x.entity.id not in named)][:CANDIDATES_PER_MEMBER]
    outside: dict[str, SlimEntity] = {r.entity.id: r.entity for lst in cands.values() for _, r in lst if r.entity.id not in group_rank}
    scored: dict[str, float] = {}
    if outside and average:
        async with sem:
            try:
                scored = await group_affinity(client, domain, profile, list(outside.values()))
            except QlooError as exc:
                log.warning("group affinity lookup failed for %s: status=%s", domain, exc.status)

    def fit(r: Recommendation) -> tuple[str, int | None, float | None] | None:
        eid = r.entity.id
        if eid in group_rank:
            own = r.entity.affinity
            return "in_group_results", group_rank[eid], (own / average if own is not None and average else None)
        ratio = scored[eid] / average if eid in scored and average else None
        return ("group_affinity", None, ratio) if ratio is not None and ratio >= GROUP_FIT_RATIO else None

    fitting = {m: [(rank, r, f) for rank, r in lst if (f := fit(r))] for m, lst in cands.items()}
    picks: list[PersonalPick] = []
    taken: set[str] = set()
    for m in sorted(fitting, key=lambda x: len(fitting[x])):    # most constrained member chooses first
        options = fitting[m]
        if not options:
            continue
        rank, rec, (kind, g_rank, ratio) = next(((a, b, c) for a, b, c in options if b.entity.id not in taken), options[0])  # prefer one nobody else has
        taken.add(rec.entity.id)
        via = rec.why[0].via if rec.why else []
        picks.append(PersonalPick(member=m, domain=domain, entity=rec.entity, via=via, member_rank=rank, fit=kind,  # type: ignore[arg-type]
                                  group_rank=g_rank, group_ratio=round(ratio, 3) if ratio is not None else None,
                                  explanation=explain_personal(m, domain, via, rank, kind, g_rank, ratio)))
    have = {p.member for p in picks}
    skips = []
    for m in members:
        if m in have:
            continue
        res = got[m]
        reason, note = (("no_signal", f"None of their tastes give Qloo anything to work with for {LABEL[domain]}.") if res == "no_signal"
                        else ("qloo_error", "Qloo was busy, so their personal pick could not be looked up. Rebuilding the plan usually fixes this.") if res == "qloo_error"
                        else ("none_fit_group", f"Qloo's best results for their tastes alone are too far from the group's taste to suggest "
                                                f"(its top {CANDIDATES_PER_MEMBER} new {LABEL[domain]} results were all below {round(GROUP_FIT_RATIO * 100)}% of the group's average pull)."))
        skips.append(PersonalSkip(member=m, domain=domain, reason=reason, note=note))  # type: ignore[arg-type]
    return sorted(picks, key=lambda p: members.index(p.member)), skips


async def compute(client, resolved: list[ResolvedTaste], results: dict[str, list[Recommendation]], queries: dict[str, DomainQuery],
                  members: list[str], domains: tuple[str, ...] | None = None) -> tuple[list[PersonalPick], list[PersonalSkip]]:
    """Personal picks for `domains` (default: music and content, whichever the plan has)."""
    wanted = [d for d in (domains or PERSONAL_DOMAINS) if results.get(d)]
    sem = asyncio.Semaphore(CONCURRENCY)
    parts = await asyncio.gather(*[_domain(client, d, resolved, results[d], queries.get(d) or DomainQuery(PlanOptions()), members, sem) for d in wanted])
    return [p for ps, _ in parts for p in ps], [s for _, ss in parts for s in ss]


async def run(client, resolved, results, queries, members, domains=None, trace: list[TraceStep] | None = None,
              ) -> tuple[list[PersonalPick], list[PersonalSkip]]:
    """compute(), never raising (personal picks are an extra, not a dependency), and recording one visible trace step."""
    t0 = time.perf_counter()
    try:
        picks, skips = await compute(client, resolved, results, queries, members, domains)
    except Exception as exc:  # noqa: BLE001
        log.warning("personal picks failed: %s: %s", type(exc).__name__, str(exc)[:160])
        if trace is not None:
            trace.append(TraceStep(step=len(trace) + 1, tool="personal_picks", args={}, summary=f"Skipped: {type(exc).__name__}",
                                   ms=int((time.perf_counter() - t0) * 1000), ok=False))
        return [], []
    wanted = [d for d in (domains or PERSONAL_DOMAINS) if results.get(d)]
    if trace is not None and wanted:
        covered = len({p.member for p in picks})
        trace.append(TraceStep(
            step=len(trace) + 1, tool="personal_picks", args={"domains": ", ".join(wanted), "members": len(members)},
            summary=f"Asked Qloo what each member would like on their own, then kept results that also fit the group: "
                    f"{covered} of {len(members)} members got a personal pick.",
            ms=int((time.perf_counter() - t0) * 1000), ok=True))
    return picks, skips
