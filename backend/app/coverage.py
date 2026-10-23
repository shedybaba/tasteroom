"""Coverage: does every member have at least one pick that was made for them?

Two different things count, and they are kept apart everywhere (the numbers, the card, the Compare row):

- a pick that STANDS OUT for the member: their pull on it is at least STAND_OUT times an even share. These are the
  Contribution scores shown in the Why panel (normalised against each member's usual pull across the list), so the
  card and the Why bars agree. The bar is deliberately the same 1.15x used everywhere else:
  measured on the examples, lowering it flips the score from "nobody" to "everybody" within a few hundredths.
- a PERSONAL pick (personal.py): a Qloo result found from that member's own tastes alone that also fits the group.
  Those are made for the member by construction, so they count even though the group query can't single anyone out.

"In the lineup" means the pick is in the brief's main sections. Personal picks are shown in a separate "Something for
everyone" row, so a member can have a pick made for them without it being in the lineup. Everything is derived from data Qloo
returned: no LLM, nothing invented."""
from .brief import DOMAIN_FIELD
from .models import Coverage, MemberCoverage, PersonalPick, PickRef, PlanResponse, Recommendation
from .personal import personal_recommendation

STAND_OUT = 1.15  # same threshold as the UI (fitSummary) and the brief's "stands out for" wording
FIELD_DOMAIN = {v: k for k, v in DOMAIN_FIELD.items()}

NOT_MEASURABLE = "None of their tastes matched in Qloo, so their fit can't be measured."
NOTHING_STANDS_OUT = "No Qloo result stands out for them yet. Add more of their tastes."


class _Ctx:
    """Everything needed to evaluate coverage for one plan, computed once."""

    def __init__(self, plan: PlanResponse):
        self.plan = plan
        self.members = [m.name for m in plan.request.members]
        matched = {r.member for r in plan.resolved if r.entity is not None}
        self.measurable = [m for m in self.members if m in matched]
        self.rec: dict[str, Recommendation] = {}
        self.strength: dict[str, dict[str, float]] = {}   # entity id -> member -> multiple of an even share
        for recs in plan.recommendations.values():
            for r in recs:
                self.rec[r.entity.id] = r
                n = len(r.why)
                if n > 1:  # with one contributor "even share" is meaningless
                    self.strength[r.entity.id] = {c.member: c.score * n for c in r.why}
        # personal picks, music before content; their entities may be missing from the group lists, so they get a stand-in
        self.personal: dict[str, list[PersonalPick]] = {}
        for p in sorted(plan.personal, key=lambda p: p.domain != "music"):
            self.personal.setdefault(p.member, []).append(p)
            self.rec.setdefault(p.entity.id, personal_recommendation(p))
        self.sections: dict[str, list[str]] = {
            FIELD_DOMAIN[f]: [p.entity_id for p in getattr(plan.brief, f)] for f in DOMAIN_FIELD.values()}

    def ref(self, entity_id: str, member: str, kind: str = "standout") -> PickRef:
        r = self.rec[entity_id]
        s = self.strength.get(entity_id, {}).get(member) if kind == "standout" else None
        return PickRef(domain=r.domain, entity_id=entity_id, name=r.entity.name, kind=kind,  # type: ignore[arg-type]
                       strength=round(s, 2) if s is not None else None)

    def stands_out(self, entity_id: str, member: str) -> bool:
        return self.strength.get(entity_id, {}).get(member, 0.0) >= STAND_OUT

    def standouts(self, sections: dict[str, list[str]], member: str) -> list[str]:
        ids = [i for v in sections.values() for i in v if i in self.rec and self.stands_out(i, member)]
        return sorted(ids, key=lambda i: -self.strength[i][member])

    def personal_in(self, sections: dict[str, list[str]], member: str) -> list[str]:
        placed = {i for v in sections.values() for i in v}
        return [p.entity.id for p in self.personal.get(member, []) if p.entity.id in placed]

    def cover(self, sections: dict[str, list[str]], member: str) -> list[str]:
        """The lineup picks that serve this member (a standout, or their own personal pick)."""
        return list(dict.fromkeys(self.standouts(sections, member) + self.personal_in(sections, member)))


def compute(plan: PlanResponse) -> Coverage:
    c = _Ctx(plan)
    skipped: dict[str, str] = {}
    for s in plan.personal_skipped:
        skipped.setdefault(s.member, s.note)
    rows, covered, standout, personal, in_lineup = [], 0, 0, 0, 0
    for m in c.members:
        if m not in c.measurable:
            rows.append(MemberCoverage(member=m, covered=False, note=NOT_MEASURABLE))
            continue
        picks = [c.ref(i, m) for i in c.standouts(c.sections, m)]
        mine = c.personal.get(m, [])
        ref = c.ref(mine[0].entity.id, m, "personal") if mine else None
        lineup = bool(c.cover(c.sections, m))
        standout += bool(picks); personal += bool(mine); covered += bool(picks or mine); in_lineup += lineup
        note = None
        if not picks and not mine:
            note = skipped.get(m) or NOTHING_STANDS_OUT
        rows.append(MemberCoverage(member=m, covered=bool(picks or mine), picks=picks, personal=ref, in_lineup=lineup,
                                   note=note))
    return Coverage(members=rows, covered=covered, standout=standout, personal=personal, in_lineup=in_lineup, total=len(c.measurable),
                    unmeasurable=len(c.members) - len(c.measurable))
