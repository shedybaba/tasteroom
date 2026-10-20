"""Coverage: does every member have at least one pick that was made for them?

Two different things count, and they are kept apart everywhere (the numbers, the card, the Compare row):

- a pick that STANDS OUT for the member: their pull on it is at least STAND_OUT times an even share. These are the
  Contribution scores shown in the Why panel (normalised against each member's usual pull across the list), so the
  card, the Why bars and the swap suggestions agree. The bar is deliberately the same 1.15x used everywhere else:
  measured on the examples, lowering it flips the score from "nobody" to "everybody" within a few hundredths.
- a PERSONAL pick (personal.py): a Qloo result found from that member's own tastes alone that also fits the group.
  Those are made for the member by construction, so they count even though the group query can't single anyone out.

"In the lineup" means the pick is in the brief's main sections. Personal picks start in a separate "Something for
everyone" row; "Balance the lineup" moves them into the lineup, never letting personal picks fill a whole section (at
least one crowd-pleaser always stays, counting personal picks already there, so pressing it twice changes nothing more) and
never dropping a pick another member relies on. Everything is derived from data Qloo
returned: no LLM, nothing invented."""
from .brief import DOMAIN_FIELD, SECTIONS, reason_from_why
from .models import Brief, BriefPick, Coverage, MemberCoverage, PersonalPick, PickRef, PlanResponse, Recommendation, Swap
from .personal import personal_recommendation

STAND_OUT = 1.15  # same threshold as the UI (fitSummary) and the brief's "stands out for" wording
SECTION_CAP = {domain: cap for domain, cap in SECTIONS.values()}
MAX_PERSONAL = {domain: cap - 1 for domain, cap in SECTIONS.values()}   # every section keeps at least one crowd-pleaser
FIELD_DOMAIN = {v: k for k, v in DOMAIN_FIELD.items()}

NOT_MEASURABLE = "None of their tastes matched in Qloo, so their fit can't be measured."
NOTHING_STANDS_OUT = "No Qloo result stands out for them yet. Add more of their tastes."
NO_ROOM = "Their personal pick stays in \"Something for everyone\": every section of the lineup keeps at least one crowd-pleaser."


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

    def swap_for(self, sections: dict[str, list[str]], member: str, used: dict[str, int]) -> Swap | None:
        """What would put `member` in the lineup: their personal pick, or (only if they have none) a real result that stands out for them.
        It takes a free slot, or replaces the pick that matters to the fewest members (never one that is the only pick
        serving someone, never the headline venue). Personal picks never fill a whole section (`used` counts those already there)."""
        in_plan = {i for v in sections.values() for i in v}
        if self.personal.get(member):   # a member with a personal pick is balanced with that pick or not at all
            cands = [p.entity.id for p in self.personal[member] if p.entity.id not in in_plan]
        else:                           # no personal pick (e.g. their query found nothing that fits the group): a real standout result
            cands = sorted((i for i in self.strength if i not in in_plan and self.stands_out(i, member)), key=lambda i: -self.strength[i][member])
        covers = {m: self.cover(sections, m) for m in self.measurable}
        for cand in cands:
            domain = self.rec[cand].domain
            if used.get(domain, 0) >= MAX_PERSONAL.get(domain, 0):
                continue
            kind = "personal" if any(p.entity.id == cand for p in self.personal.get(member, [])) else "standout"
            ids = sections.get(domain, [])
            if len(ids) < SECTION_CAP.get(domain, 0):
                return Swap(member=member, add=self.ref(cand, member, kind))
            options = []
            for pos, pid in enumerate(ids):
                if domain == "venues" and pos == 0:
                    continue
                if any(covers[m] == [pid] for m in self.measurable if m != member):
                    continue
                options.append((sum(pid in covers[m] for m in self.measurable), -pos, pid))   # fewest dependants; then lowest-ranked
            if options:
                return Swap(member=member, add=self.ref(cand, member, kind), drop=self.ref(min(options)[2], member, "standout"))
        return None


def plan_swaps(plan: PlanResponse, ctx: _Ctx | None = None) -> list[Swap]:
    """The swaps "Balance the lineup" would make: one per member who has nothing in the lineup yet, applied in order and each
    judged against the brief as already changed by the earlier ones."""
    c = ctx or _Ctx(plan)
    sections = {d: list(ids) for d, ids in c.sections.items()}
    personal_ids = {p.entity.id for ps in c.personal.values() for p in ps}
    used = {d: sum(i in personal_ids for i in ids) for d, ids in sections.items()}   # personal picks already in each section
    swaps: list[Swap] = []
    for m in c.measurable:
        if c.cover(sections, m):
            continue
        swap = c.swap_for(sections, m, used)
        if swap is None:
            continue
        ids = sections.setdefault(swap.add.domain, [])
        if swap.drop:
            ids[ids.index(swap.drop.entity_id)] = swap.add.entity_id
        else:
            ids.append(swap.add.entity_id)
        used[swap.add.domain] = used.get(swap.add.domain, 0) + 1
        swaps.append(swap)
    return swaps


def compute(plan: PlanResponse) -> Coverage:
    c = _Ctx(plan)
    balance = plan_swaps(plan, c)
    swap_for_member = {s.member: s for s in balance}   # the rows promise exactly what the button will do, no more
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
        suggestion = None if lineup else swap_for_member.get(m)
        note = None
        if not picks and not mine:
            note = skipped.get(m) or NOTHING_STANDS_OUT
        elif not lineup and suggestion is None:
            note = NO_ROOM
        rows.append(MemberCoverage(member=m, covered=bool(picks or mine), picks=picks, personal=ref, in_lineup=lineup,
                                   note=note, suggestion=suggestion))
    return Coverage(members=rows, covered=covered, standout=standout, personal=personal, in_lineup=in_lineup, total=len(c.measurable),
                    unmeasurable=len(c.members) - len(c.measurable), balance=balance)


def _reason(c: _Ctx, s: Swap) -> str:
    """Templated reason for a swapped-in pick: a personal pick keeps its own data-built explanation."""
    mine = next((p for p in c.personal.get(s.member, []) if p.entity.id == s.add.entity_id), None)
    return mine.explanation if mine else reason_from_why(c.rec[s.add.entity_id])


def apply_swaps(plan: PlanResponse, swaps: list[Swap]) -> Brief:
    """The brief with the swaps made: same sections, picks replaced or added. New picks get a reason built from their Qloo
    data (the brief writer rewrites it afterwards)."""
    c = _Ctx(plan)
    data = plan.brief.model_dump()
    for s in swaps:
        picks = data[DOMAIN_FIELD[s.add.domain]]
        new = BriefPick(entity_id=s.add.entity_id, name=s.add.name, reason=_reason(c, s)).model_dump()
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
        new = BriefPick(entity_id=s.add.entity_id, name=s.add.name, reason=_reason(c, s)).model_dump()
        slot = next((i for i, p in enumerate(picks) if s.drop and p["entity_id"] == s.drop.entity_id), None)
        if slot is not None:
            picks[slot] = new
        elif len(picks) < SECTION_CAP[s.add.domain]:
            picks.append(new)
        else:
            picks[-1] = new
    return Brief(**data)
