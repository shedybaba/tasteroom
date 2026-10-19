"""Why was this picked? Built only from data Qloo returned, never invented.

Method A (qloo_explainability): Qloo's per-result score split across the input entities. Each input
entity is mapped back to the member(s) who named it (an entity named by several members splits its
share evenly). Qloo's split is close to uniform, so raw shares mostly track how many tastes a member
listed. We therefore divide each member's share by the share their entity count alone would predict
("lift") and normalise: equal scores mean the pick suits everyone about equally; a higher score is a
real extra pull. `via` lists the member's entities that share the most tags with the result.
Even lift is not enough on its own: some members' entities are simply central in Qloo's graph, so they
carry a near-constant share on EVERY result of a query (measured: sd 0.005 across picks). That says
who dominates the query, not why a pick was chosen. relative_to_list() therefore compares each member's
pull on a pick with that member's usual (median) pull across the whole list and renormalises, so only
pick-specific deviations remain.
Method C (tag_overlap): fallback when Qloo returned no explainability. Members are credited by how
many non-generic tags their entities share with the result.
`shared_tags` is always computed from tag overlap; it makes the "why" text richer.
"""
from collections import Counter, defaultdict
from statistics import median

from .models import Contribution, Recommendation, SlimEntity
from .profile import Profile

# Qloo adds generic audience/collection tags ("Loyal", "Canonical") to nearly everything.
GENERIC_TAG_PREFIXES = ("urn:tag:audience:", "urn:tag:collection:")
MAX_VIA = 3
MAX_SHARED_TAGS = 5


# Taxonomy labels that describe how Qloo files an entity, not taste ("B2C", "Other", "Podcasts").
NOISE_TAG_NAMES = {"b2c", "b2b", "other", "corporate brand", "podcasts", "advertising", "canonical"}


def _label(pe) -> str:
    return pe.display or pe.entity.name


def _specific(tag_id: str) -> bool:
    return not tag_id.startswith(GENERIC_TAG_PREFIXES)


def shared_tags(entity: SlimEntity, profile: Profile, limit: int = MAX_SHARED_TAGS) -> list[str]:
    """Tag names the result shares with the community's entities, most widely shared first."""
    counts: Counter[str] = Counter()
    for pe in profile.entities.values():
        counts.update({t for t in pe.entity.tag_ids if _specific(t)})
    hits = [(counts[tid], -i, name) for i, (tid, name) in enumerate(zip(entity.tag_ids, entity.tags))
            if _specific(tid) and counts[tid] > 0 and name.lower() not in NOISE_TAG_NAMES]
    hits.sort(reverse=True)
    return [name for _, _, name in hits[:limit]]


def _native(entity: SlimEntity, profile: Profile, signal_ids: list[str]) -> list[Contribution]:
    n = len(signal_ids)
    share: dict[str, float] = defaultdict(float)
    expected: dict[str, float] = defaultdict(float)
    owned: dict[str, list[str]] = defaultdict(list)
    for eid in signal_ids:
        pe = profile.entities.get(eid)
        if pe is None:
            continue
        for member in pe.members:
            share[member] += entity.explain.get(eid, 0.0) / len(pe.members)
            expected[member] += 1 / n / len(pe.members)
            owned[member].append(eid)
    lift = {m: share[m] / expected[m] for m in share if share[m] > 0 and expected[m] > 0}
    total = sum(lift.values())
    result_tags = {t for t in entity.tag_ids if _specific(t)}

    def rank(eid: str) -> tuple[int, float]:
        tags = len(result_tags & {t for t in profile.entities[eid].entity.tag_ids if _specific(t)})
        return tags, entity.explain.get(eid, 0.0)

    out = [
        Contribution(
            member=m, score=round(v / total, 4),
            via=[_label(profile.entities[e]) for e in sorted(owned[m], key=rank, reverse=True)[:MAX_VIA]],
        )
        for m, v in lift.items()
    ]
    return sorted(out, key=lambda c: -c.score)


def _tag_overlap(entity: SlimEntity, profile: Profile) -> list[Contribution]:
    result_tags = {t for t in entity.tag_ids if _specific(t)}
    raw: dict[str, int] = {}
    via: dict[str, list[tuple[int, str]]] = {}
    for member in profile.members:
        total, rows = 0, []
        for eid in profile.member_ids(member):
            n = len(result_tags & {t for t in profile.entities[eid].entity.tag_ids if _specific(t)})
            if n:
                total += n
                rows.append((n, _label(profile.entities[eid])))
        if total:
            raw[member], via[member] = total, rows
    grand = sum(raw.values())
    out = [Contribution(member=m, score=round(v / grand, 4), via=[n for _, n in sorted(via[m], reverse=True)[:MAX_VIA]])
           for m, v in raw.items()]
    return sorted(out, key=lambda c: -c.score)


def relative_to_list(recs: list[Recommendation]) -> list[Recommendation]:
    """Re-express native contributions relative to each member's usual (median) pull across `recs`
    (needs 3+ results to mean anything; the median keeps one outlier pick from skewing "usual").
    Mutates and returns the same list."""
    if len(recs) < 3:
        return recs
    scores: dict[str, list[float]] = defaultdict(list)
    for r in recs:
        if r.explanation_method == "qloo_explainability":
            for c in r.why:
                scores[c.member].append(c.score)
    mean = {m: median(v) for m, v in scores.items() if median(v) > 0}
    for r in recs:
        if r.explanation_method != "qloo_explainability":
            continue
        adj = {c.member: c.score / mean[c.member] for c in r.why if c.member in mean}
        norm = sum(adj.values())
        if norm > 0:
            via = {c.member: c.via for c in r.why}
            r.why = sorted((Contribution(member=m, score=round(v / norm, 4), via=via[m]) for m, v in adj.items()),
                           key=lambda c: -c.score)
    return recs


def explain(entity: SlimEntity, domain: str, profile: Profile, signal_ids: list[str] | None = None) -> Recommendation:
    """`signal_ids` = the entity ids that were sent to Qloo for this query (default: whole profile)."""
    why = _native(entity, profile, signal_ids or profile.ids()) if entity.explain else []
    method = "qloo_explainability"
    if not why:
        why, method = _tag_overlap(entity, profile), "tag_overlap"
    return Recommendation(
        entity=entity, domain=domain, why=why,  # type: ignore[arg-type]
        shared_tags=shared_tags(entity, profile), explanation_method=method,  # type: ignore[arg-type]
    )
