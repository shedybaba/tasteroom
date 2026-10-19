"""Why was this picked? Built only from data Qloo returned, never invented.

Method A (qloo_explainability): Qloo's per-result score split across the input entities. Each input
entity is mapped back to the member(s) who named it (an entity named by several members splits its
share evenly). Qloo's split is close to uniform, so raw shares mostly track how many tastes a member
listed. We therefore divide each member's share by the share their entity count alone would predict
("lift") and normalise: equal scores mean the pick suits everyone about equally; a higher score is a
real extra pull. `via` lists the member's entities that share the most tags with the result.
Method C (tag_overlap): fallback when Qloo returned no explainability. Members are credited by how
many non-generic tags their entities share with the result.
`shared_tags` is always computed from tag overlap; it makes the "why" text richer.
"""
from collections import Counter, defaultdict

from .models import Contribution, Recommendation, SlimEntity
from .profile import Profile

# Qloo adds generic audience/collection tags ("Loyal", "Canonical") to nearly everything.
GENERIC_TAG_PREFIXES = ("urn:tag:audience:", "urn:tag:collection:")
MAX_VIA = 3
MAX_SHARED_TAGS = 5


def _specific(tag_id: str) -> bool:
    return not tag_id.startswith(GENERIC_TAG_PREFIXES)


def shared_tags(entity: SlimEntity, profile: Profile, limit: int = MAX_SHARED_TAGS) -> list[str]:
    """Tag names the result shares with the community's entities, most widely shared first."""
    counts: Counter[str] = Counter()
    for pe in profile.entities.values():
        counts.update({t for t in pe.entity.tag_ids if _specific(t)})
    hits = [(counts[tid], -i, name) for i, (tid, name) in enumerate(zip(entity.tag_ids, entity.tags))
            if _specific(tid) and counts[tid] > 0]
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
            via=[profile.entities[e].entity.name for e in sorted(owned[m], key=rank, reverse=True)[:MAX_VIA]],
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
                rows.append((n, profile.entities[eid].entity.name))
        if total:
            raw[member], via[member] = total, rows
    grand = sum(raw.values())
    out = [Contribution(member=m, score=round(v / grand, 4), via=[n for _, n in sorted(via[m], reverse=True)[:MAX_VIA]])
           for m, v in raw.items()]
    return sorted(out, key=lambda c: -c.score)


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
