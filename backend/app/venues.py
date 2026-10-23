"""Venues: a labelled "Top pick" and "Cheapest option", both taken from the same Qloo venue results.

- Top pick: the brief's first venue, i.e. the venue that fits the group best (unchanged logic).
- Cheapest option: the venue with the lowest Qloo `price_level` among that city's venue results (ties go to the better-ranked
  venue). If the top pick has that same level it is both, and is shown once.
- A venue Qloo has no price for is never given one: it is shown as "Price not available". If no venue has a price there is
  no cheapest option at all.

After the brief is written (new plan, refinement) the cheapest option is put in the venue section right after the top
pick, with a reason built from Qloo data. Pure function, nothing invented, idempotent."""
from .brief import SECTIONS, fit_phrase
from .models import Brief, BriefPick, PlanResponse, Recommendation, VenueChoice

CAP = SECTIONS["venue"][1]


def cheapest(results: list[Recommendation]) -> Recommendation | None:
    priced = [(r.entity.price_level, i, r) for i, r in enumerate(results) if r.entity.price_level]
    return min(priced, key=lambda t: (t[0], t[1]))[2] if priced else None


def venue_choice(plan: PlanResponse) -> VenueChoice:
    venues = plan.recommendations.get("venues") or []
    top_id = plan.brief.venue[0].entity_id if plan.brief.venue else None
    low = cheapest(venues)
    top = next((r for r in venues if r.entity.id == top_id), None)
    both = bool(low and top and top.entity.price_level == low.entity.price_level)
    return VenueChoice(top_id=top_id, cheapest_id=(top_id if both else (low.entity.id if low else None)), top_is_cheapest=both,
                       cheapest_level=low.entity.price_level if low else None,
                       priced=sum(1 for r in venues if r.entity.price_level), total=len(venues))


def _reason(rec: Recommendation, priced: int, city: str) -> str:
    level = rec.entity.price_level or 0
    where = city.strip() or "your city"
    return (f"Cheapest option: price level {level} of 4 ({'$' * level}), the lowest of the {priced} venue{'s' if priced != 1 else ''} "
            f"Qloo returned for {where} that list a price. Group fit: {fit_phrase(rec)}.")


def enforce_venues(brief: Brief, results: list[Recommendation], city: str) -> Brief:
    """The brief with the cheapest option right after the top pick (replacing the last backup if the section is full)."""
    if not brief.venue or not results:
        return brief
    low = cheapest(results)
    if low is None:
        return brief
    top = brief.venue[0]
    top_rec = next((r for r in results if r.entity.id == top.entity_id), None)
    if low.entity.id == top.entity_id or (top_rec and top_rec.entity.price_level == low.entity.price_level):
        return brief   # the top pick is the cheapest (or tied for it): shown once, with both labels
    priced = sum(1 for r in results if r.entity.price_level)
    new = BriefPick(entity_id=low.entity.id, name=low.entity.name, reason=_reason(low, priced, city))
    picks = [top, new] + [p for p in brief.venue[1:] if p.entity_id != low.entity.id]
    return brief.model_copy(update={"venue": picks[:CAP]})
