"""Coverage: does every member have at least one pick that was made for them?

A pick "stands out" for a member when that member's pull on it is at least STAND_OUT times an even share. The numbers
are the Contribution scores already shown in the Why panel (normalised against each member's usual pull across the
list), so this card, the Why bars and the swap suggestions always agree. Everything is derived from data Qloo
returned: no LLM, nothing invented. The bar is deliberately the same 1.15x used everywhere else. Measured on the
saved examples, lowering it flips the score from "nobody" to "everybody" within a few hundredths, which would make the
number meaningless, so a member whom Qloo cannot tell apart from the group is reported as such, not swapped for noise."""
from .brief import DOMAIN_FIELD, SECTIONS, reason_from_why
from .models import Brief, BriefPick, Coverage, MemberCoverage, PickRef, PlanResponse, Recommendation, Swap

STAND_OUT = 1.15  # same threshold as the UI (fitSummary) and the brief's "stands out for" wording
SECTION_CAP = {domain: cap for domain, cap in SECTIONS.values()}
FIELD_DOMAIN = {v: k for k, v in DOMAIN_FIELD.items()}

NOT_MEASURABLE = "None of their tastes matched in Qloo, so their fit can't be measured."
NOTHING_STANDS_OUT = "No Qloo result stands out for them yet. Add more of their tastes."


class _Ctx:
    """Everything needed to evaluate coverage for one plan, computed once."""

    def __init__(self, plan: PlanResponse):
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
        self.sections: dict[str, list[str]] = {
            FIELD_DOMAIN[f]: [p.entity_id for p in getattr(plan.brief, f)] for f in DOMAIN_FIELD.values()}

    def ref(self, entity_id: str, member: str) -> PickRef:
        r = self.rec[entity_id]
        return PickRef(domain=r.domain, entity_id=entity_id, name=r.entity.name,
                       strength=round(self.strength.get(entity_id, {}).get(member, 1.0), 2))

    def stands_out(self, entity_id: str, member: str) -> bool:
        return self.strength.get(entity_id, {}).get(member, 0.0) >= STAND_OUT

    def standouts(self, sections: dict[str, list[str]], member: str) -> list[str]:
        ids = [i for v in sections.values() for i in v if i in self.rec and self.stands_out(i, member)]
        return sorted(ids, key=lambda i: -self.strength[i][member])

    def swap_for(self, sections: dict[str, list[str]], member: str) -> Swap | None:
        """The strongest real Qloo result, not yet in the brief, that stands out for `member`, plus the pick it replaces
        (None when the section has room). A pick that is the only one made for someone else is never replaced, and the
        headline venue is never replaced."""
        in_plan = {i for v in sections.values() for i in v}
        cands = sorted((i for i in self.strength if i not in in_plan and self.stands_out(i, member)),
                       key=lambda i: -self.strength[i][member])
        covers = {m: self.standouts(sections, m) for m in self.measurable}
        for cand in cands:
            domain = self.rec[cand].domain
            ids = sections.get(domain, [])
            if len(ids) < SECTION_CAP.get(domain, 0):
                return Swap(member=member, add=self.ref(cand, member))
            options = []
            for pos, pid in enumerate(ids):
                if domain == "venues" and pos == 0:
                    continue
                if any(covers[m] == [pid] for m in self.measurable if m != member):
                    continue
                # replace the pick that matters to the fewest members; on a tie the lowest-ranked one
                options.append((sum(self.stands_out(pid, m) for m in self.measurable), -pos, pid))
            if options:
                return Swap(member=member, add=self.ref(cand, member), drop=self.ref(min(options)[2], member))
        return None


def plan_swaps(plan: PlanResponse, ctx: _Ctx | None = None) -> list[Swap]:
    """The swaps "Balance the lineup" would make: one per uncovered member, applied in order and each judged against the
    brief as already changed by the earlier ones, so one swap that covers several members is not repeated."""
    c = ctx or _Ctx(plan)
    sections = {d: list(ids) for d, ids in c.sections.items()}
    swaps: list[Swap] = []
    for m in c.measurable:
        if c.standouts(sections, m):
            continue
        swap = c.swap_for(sections, m)
        if swap is None:
            continue
        ids = sections.setdefault(swap.add.domain, [])
        if swap.drop:
            ids[ids.index(swap.drop.entity_id)] = swap.add.entity_id
        else:
            ids.append(swap.add.entity_id)
        swaps.append(swap)
    return swaps


def compute(plan: PlanResponse) -> Coverage:
    c = _Ctx(plan)
    rows, covered = [], 0
    for m in c.members:
        if m not in c.measurable:
            rows.append(MemberCoverage(member=m, covered=False, note=NOT_MEASURABLE))
            continue
        picks = [c.ref(i, m) for i in c.standouts(c.sections, m)]
        covered += bool(picks)
        if picks:
            rows.append(MemberCoverage(member=m, covered=True, picks=picks))
        else:
            swap = c.swap_for(c.sections, m)
            rows.append(MemberCoverage(member=m, covered=False, suggestion=swap, note=None if swap else NOTHING_STANDS_OUT))
    return Coverage(members=rows, covered=covered, total=len(c.measurable), unmeasurable=len(c.members) - len(c.measurable),
                    balance=plan_swaps(plan, c))


def apply_swaps(plan: PlanResponse, swaps: list[Swap]) -> Brief:
    """The brief with the swaps made: same sections, picks replaced or added. New picks get a reason built from their
    Qloo explanation data (the brief writer rewrites it afterwards)."""
    c = _Ctx(plan)
    data = plan.brief.model_dump()
    for s in swaps:
        picks = data[DOMAIN_FIELD[s.add.domain]]
        new = BriefPick(entity_id=s.add.entity_id, name=s.add.name, reason=reason_from_why(c.rec[s.add.entity_id])).model_dump()
        if s.drop:
            picks[[p["entity_id"] for p in picks].index(s.drop.entity_id)] = new
        else:
            picks.append(new)
    return Brief(**data)


def enforce_swaps(brief: Brief, plan: PlanResponse, swaps: list[Swap]) -> Brief:
    """Guarantee after the brief writer ran that every swap is in the brief (the writer is asked to keep them, this makes
    it certain). A missing pick takes the place of the pick it was meant to replace, or is appended."""
    c = _Ctx(plan)
    data = brief.model_dump()
    for s in swaps:
        picks = data[DOMAIN_FIELD[s.add.domain]]
        if any(p["entity_id"] == s.add.entity_id for p in picks):
            continue
        new = BriefPick(entity_id=s.add.entity_id, name=s.add.name, reason=reason_from_why(c.rec[s.add.entity_id])).model_dump()
        slot = next((i for i, p in enumerate(picks) if s.drop and p["entity_id"] == s.drop.entity_id), None)
        if slot is not None:
            picks[slot] = new
        elif len(picks) < SECTION_CAP[s.add.domain]:
            picks.append(new)
        else:
            picks[-1] = new
    return Brief(**data)
