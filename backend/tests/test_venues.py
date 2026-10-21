"""Top pick + Cheapest option: both from the same Qloo venue results, never guessed."""
import json
from pathlib import Path

import pytest

from app import venues
from app.models import Brief, BriefPick, Contribution, PlanResponse, Recommendation, SlimEntity
from app.slim import slim_entity

PRECOMPUTED = Path(__file__).resolve().parents[1] / "precomputed"


def rec(i: str, name: str, level: int | None) -> Recommendation:
    return Recommendation(entity=SlimEntity(id=i, name=name, type="urn:entity:place", price_level=level), domain="venues",
                          why=[Contribution(member="Ada", score=0.5, via=[]), Contribution(member="Bo", score=0.5, via=[])],
                          shared_tags=[], explanation_method="qloo_explainability")


def brief(*ids: str) -> Brief:
    return Brief(title="t", concept="c", vibe_words=["v"], run_of_show=["r"], promo_line="p", music=[], sponsors=[], content=[],
                 venue=[BriefPick(entity_id=i, name=i, reason=f"LLM reason {i}") for i in ids])


RESULTS = [rec("A", "Alpha", 3), rec("B", "Bravo", 2), rec("C", "Charlie", 1), rec("D", "Delta", None), rec("E", "Echo", 1)]


def test_price_level_is_read_from_qloo_only_and_never_guessed():
    p = lambda v: slim_entity({"entity_id": "x", "name": "n", "properties": {"price_level": v}}).price_level  # noqa: E731
    assert [p(2), p(2.0), p("3"), p("$$"), p(None), p(0), p(7), p(True), p("cheap"), p("")] == [2, 2, 3, 2, None, None, None, None, None, None]
    assert slim_entity({"entity_id": "x", "name": "n"}).price_level is None


def test_the_cheapest_is_the_lowest_price_level_and_ties_go_to_the_better_ranked_venue():
    assert venues.cheapest(RESULTS).entity.id == "C"            # level 1, ranked above Echo (also level 1)
    assert venues.cheapest([rec("A", "A", None), rec("B", "B", None)]) is None


def test_the_cheapest_option_is_added_right_after_the_top_pick_and_the_top_pick_stays_first():
    out = venues.enforce_venues(brief("A", "B", "D"), RESULTS, "Lagos")
    assert [p.entity_id for p in out.venue] == ["A", "C", "B"]                    # D (a backup) made room; cap is 3
    assert out.venue[0].reason == "LLM reason A"                                  # the top pick keeps its own reason
    assert out.venue[1].reason.startswith("Cheapest option: price level 1 of 4 ($)") and "Lagos" in out.venue[1].reason
    assert "the lowest of the 4 venues" in out.venue[1].reason                    # 4 of the 5 venues list a price


def test_a_cheapest_venue_the_brief_already_has_moves_next_to_the_top_pick_and_is_not_duplicated():
    out = venues.enforce_venues(brief("A", "B", "C"), RESULTS, "Lagos")
    assert [p.entity_id for p in out.venue] == ["A", "C", "B"]


def test_it_is_idempotent():
    once = venues.enforce_venues(brief("A", "B", "D"), RESULTS, "Lagos")
    assert venues.enforce_venues(once, RESULTS, "Lagos") == once


def test_when_the_top_pick_is_the_cheapest_nothing_is_added():
    b = brief("C", "A", "B")
    assert venues.enforce_venues(b, RESULTS, "Lagos") == b


def test_a_top_pick_tied_for_the_lowest_price_counts_as_the_cheapest_too():
    b = brief("E", "A", "B")                                                       # Echo and Charlie are both level 1
    assert venues.enforce_venues(b, RESULTS, "Lagos") == b


def test_with_no_price_data_nothing_is_invented():
    results = [rec("A", "Alpha", None), rec("B", "Bravo", None)]
    b = brief("A", "B")
    assert venues.enforce_venues(b, results, "Lagos") == b
    assert venues.enforce_venues(Brief(**{**b.model_dump(), "venue": []}), results, "Lagos").venue == []


def plan_with(results: list[Recommendation], b: Brief) -> PlanResponse:
    base = PlanResponse.model_validate(json.loads((PRECOMPUTED / "lagos-creators.json").read_text())["plan"])
    return base.model_copy(update={"recommendations": {**base.recommendations, "venues": results}, "brief": b})


@pytest.mark.parametrize("ids,top_is_cheapest,cheapest_id", [(("A", "C"), False, "C"), (("C", "A"), True, "C"), (("E", "A"), True, "E")])
def test_the_plan_exposes_which_venue_is_the_top_pick_and_which_is_the_cheapest(ids, top_is_cheapest, cheapest_id):
    vc = plan_with(RESULTS, brief(*ids)).venue_choice
    assert vc.top_id == ids[0] and vc.cheapest_id == cheapest_id and vc.top_is_cheapest is top_is_cheapest
    assert vc.cheapest_level == 1 and vc.priced == 4 and vc.total == 5


def test_the_plan_says_so_when_no_venue_has_a_price():
    vc = plan_with([rec("A", "Alpha", None)], brief("A")).venue_choice
    assert vc.cheapest_id is None and vc.cheapest_level is None and vc.priced == 0 and vc.top_id == "A"


@pytest.mark.parametrize("eid", ("lagos-creators", "pixel-pact", "sunrise-run-club"))
def test_every_saved_example_labels_its_venues_consistently(eid):
    plan = PlanResponse.model_validate(json.loads((PRECOMPUTED / f"{eid}.json").read_text())["plan"])
    vc, ids = plan.venue_choice, [p.entity_id for p in plan.brief.venue]
    assert ids[0] == vc.top_id and len(ids) <= 3
    if vc.cheapest_id is None:
        assert vc.priced == 0                                                      # no price data: honest, nothing labelled cheapest
    else:
        assert vc.cheapest_id in ids
        by_id = {r.entity.id: r.entity.price_level for r in plan.recommendations["venues"]}
        assert by_id[vc.cheapest_id] == min(v for v in by_id.values() if v)        # really the lowest level among the results
        if not vc.top_is_cheapest:
            assert ids[1] == vc.cheapest_id and plan.brief.venue[1].reason.startswith("Cheapest option:")
