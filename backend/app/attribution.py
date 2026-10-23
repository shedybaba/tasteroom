"""Who a lineup pick was chosen for.

A personal pick (personal.py) that sits in the brief's main lineup must say so, whatever wrote the brief's prose: the LLM's
reason for it tends to be group wording ("stands out for Tessa", "fits all 7 members") that never names the member it was
chosen for. So after every brief is written (new plan, refinement) this step replaces the reason of every lineup pick
that is somebody's personal pick with one built from Qloo's data, led by that member's name:

    Personal pick for Priya: Qloo's top match for their tastes (YOASOBI, Jujutsu Kaisen), and it fits the group too: it is #2 in
    the group's music results. It also stands out for Tessa.

The first sentence is the personal pick's own data (rank in the member's list, which of their tastes it came from, how it
fits the group). The second sentence is added only when the group data supports it: another member's pull on it is at least
STAND_OUT times an even share, or it is a crowd-pleaser (nobody stands out) in a real group result. The group wording never
replaces the member's name. Pure function, nothing invented, idempotent."""
from .brief import SECTIONS
from .models import Brief, BriefPick, PersonalPick, Recommendation
from .personal import fit_text

STAND_OUT = 1.15  # same bar as the Why panel, coverage and the brief's "stands out for" wording


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def members_for(personal: list[PersonalPick], domain: str, entity_id: str) -> list[PersonalPick]:
    """Every member's personal pick that is this entity (usually one; two members can land on the same result)."""
    return [p for p in personal if p.domain == domain and p.entity.id == entity_id]


def _own(p: PersonalPick, solo: bool) -> str:
    rank = "top match" if p.member_rank == 1 else f"#{p.member_rank} match"
    via = f" ({', '.join(p.via[:3])})" if p.via else ""
    return f"{rank} for {'their' if solo else p.member + chr(39) + 's'} tastes{via}"


def group_sentence(rec: Recommendation | None, names: list[str]) -> str | None:
    """What the group data says about this pick beyond the member it was chosen for, or None when it says nothing true."""
    if rec is None or len(rec.why) < 2:   # a stand-in with one contributor is not group data
        return None
    n = len(rec.why)
    others = [c.member for c in sorted(rec.why, key=lambda c: -c.score) if c.score * n >= STAND_OUT and c.member not in names]
    if others:
        return f"It also stands out for {_join(others[:2])}."
    if not any(c.score * n >= STAND_OUT for c in rec.why):
        return f"It is a crowd-pleaser: it fits all {n} members."
    return None   # only the member it was chosen for stands out: nothing more to say


def personal_reason(mine: list[PersonalPick], group: Recommendation | None) -> str:
    names = [p.member for p in mine]
    first = mine[0]
    own = " and ".join(_own(p, solo=len(mine) == 1) for p in mine)
    text = f"Personal pick for {_join(names)}: Qloo's {own}, and it fits the group too: {fit_text(first.domain, first.fit, first.group_rank, first.group_ratio)}."
    extra = group_sentence(group, names)
    return f"{text} {extra}" if extra else text


def attribute(brief: Brief, personal: list[PersonalPick], results: dict[str, list[Recommendation]]) -> Brief:
    """The brief with every lineup pick that is a member's personal pick explained as one. `results` are the plan's group
    results (their `why` gives the group wording)."""
    if not personal:
        return brief
    data = brief.model_dump()
    for field, (domain, _cap) in SECTIONS.items():
        group = {r.entity.id: r for r in results.get(domain, [])}
        out = []
        for pick in getattr(brief, field):
            mine = members_for(personal, domain, pick.entity_id)
            out.append(BriefPick(entity_id=pick.entity_id, name=pick.name, reason=personal_reason(mine, group.get(pick.entity_id))) if mine else pick)
        data[field] = [p.model_dump() for p in out]
    return Brief(**data)
