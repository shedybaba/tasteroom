"""Coverage: who has a pick made for them, and "Balance the lineup" (swaps drawn from existing Qloo results only)."""
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from limits import parse

from app import coverage, main, ratelimit, refine
from app.brief import DOMAIN_FIELD
from app.models import Contribution, PlanResponse
from app.tools import PlanError
from tests.fakes import FakeLLM

run = asyncio.run
PRECOMPUTED = Path(__file__).resolve().parents[1] / "precomputed"
EXAMPLES = ("lagos-creators", "pixel-pact", "sunrise-run-club")


def example(eid: str) -> PlanResponse:
    return PlanResponse.model_validate(json.loads((PRECOMPUTED / f"{eid}.json").read_text())["plan"])


class Offline:
    mock = False


def strength(plan: PlanResponse, entity_id: str, member: str) -> float:
    for recs in plan.recommendations.values():
        for r in recs:
            if r.entity.id == entity_id:
                return next((c.score for c in r.why if c.member == member), 0.0) * len(r.why)
    raise AssertionError(f"{entity_id} is not a Qloo result in this plan")


def brief_ids(plan: PlanResponse) -> set[str]:
    return {p.entity_id for f in DOMAIN_FIELD.values() for p in getattr(plan.brief, f)}


@pytest.mark.parametrize("eid", EXAMPLES)
def test_the_score_counts_members_with_a_standout_pick_using_the_ui_threshold(eid):
    plan = example(eid)
    cov = plan.coverage
    by_hand = 0
    for m in plan.request.members:
        mine = [i for i in brief_ids(plan) if strength(plan, i, m.name) >= 1.15]
        by_hand += bool(mine)
        row = next(r for r in cov.members if r.member == m.name)
        assert row.covered == bool(mine) and {p.entity_id for p in row.picks} == set(mine)
    assert cov.covered == by_hand and cov.total == len(plan.request.members) and cov.unmeasurable == 0


@pytest.mark.parametrize("eid", EXAMPLES)
def test_every_suggestion_is_a_real_qloo_result_that_measurably_stands_out_for_that_member(eid):
    plan = example(eid)
    in_brief = brief_ids(plan)
    suggestions = [r.suggestion for r in plan.coverage.members if r.suggestion] + plan.coverage.balance
    assert suggestions, "the examples are expected to have at least one uncovered member with a possible swap"
    for s in suggestions:
        assert s.add.entity_id not in in_brief
        assert strength(plan, s.add.entity_id, s.member) >= 1.15            # a real result, with a measurable standout
        assert s.add.strength == pytest.approx(strength(plan, s.add.entity_id, s.member), abs=0.01)
        assert plan.recommendations[s.add.domain] and s.add.entity_id in {r.entity.id for r in plan.recommendations[s.add.domain]}
        if s.drop:
            assert s.drop.entity_id in in_brief and s.drop.domain == s.add.domain


@pytest.mark.parametrize("eid", EXAMPLES)
def test_a_swap_never_uncovers_anyone_and_never_replaces_the_headline_venue(eid):
    plan = example(eid)
    before = {r.member for r in plan.coverage.members if r.covered}
    child = run(refine.balance_plan(plan, Offline(), None))
    after = {r.member for r in child.coverage.members if r.covered}
    assert before <= after and len(after) > len(before)
    assert child.brief.venue[0].entity_id == plan.brief.venue[0].entity_id
    assert child.coverage.covered > plan.coverage.covered


def test_a_member_nothing_stands_out_for_is_told_so_and_no_swap_is_invented():
    plan = example("pixel-pact")
    stuck = [r for r in plan.coverage.members if not r.covered and not r.suggestion]
    assert stuck, "pixel-pact has members whose best pull anywhere in Qloo's results is below the standout bar"
    for r in stuck:
        assert "Add more of their tastes" in r.note
        assert max(c.score * len(rec.why) for recs in plan.recommendations.values() for rec in recs for c in rec.why if c.member == r.member) < 1.15


def test_members_with_no_matched_taste_are_not_counted_either_way():
    plan = example("lagos-creators")
    resolved = [r.model_copy(update={"entity": None}) if r.member == "Tunde" else r for r in plan.resolved]
    cov = plan.model_copy(update={"resolved": resolved}).coverage
    row = next(r for r in cov.members if r.member == "Tunde")
    assert not row.covered and "can't be measured" in row.note and row.suggestion is None
    assert cov.total == 7 and cov.unmeasurable == 1


def test_coverage_is_derived_so_old_saved_plans_and_round_trips_work():
    plan = example("lagos-creators")
    data = json.loads(plan.model_dump_json())
    assert data["coverage"]["covered"] == plan.coverage.covered
    data["coverage"] = {"stale": True}                                          # a stored value is ignored, never trusted
    assert PlanResponse.model_validate(data).coverage.covered == plan.coverage.covered


def test_a_single_contributor_has_no_even_share_so_it_is_never_a_standout():
    plan = example("lagos-creators")
    first = plan.recommendations["music"][0]
    solo = first.model_copy(update={"why": [Contribution(member="Ada", score=1.0, via=[])]})
    lone = plan.model_copy(update={"recommendations": {**plan.recommendations, "music": [solo] + plan.recommendations["music"][1:]}})
    assert all(solo.entity.id != p.entity_id for r in lone.coverage.members if r.member == "Ada" for p in r.picks)


def test_balance_swaps_the_picks_and_keeps_them_even_if_the_brief_writer_drops_them():
    plan = example("lagos-creators")
    llm = FakeLLM()                       # its brief keeps only the first pick per section: the swaps must survive that
    child = run(refine.balance_plan(plan, Offline(), llm))
    wanted = {s.add.entity_id for s in plan.coverage.balance}
    assert wanted <= brief_ids(child)
    assert llm.structured_calls == 1                                            # one brief-writer call, no agent, no Qloo
    assert child.parent_id == plan.plan_id and child.version == 2 and child.refinement.instruction == "Balance the lineup"
    assert child.trace[-1].tool == "balance_lineup" and child.refinement.trace_start == len(plan.trace)
    assert child.recommendations == plan.recommendations                        # existing results only


def test_balance_with_nothing_to_do_says_why():
    child = run(refine.balance_plan(example("lagos-creators"), Offline(), None))
    with pytest.raises(PlanError, match="Nothing to balance"):
        run(refine.balance_plan(child, Offline(), None))


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(main, "llm", FakeLLM())
    for name, rate in (("_item", "100/hour"), ("_read_item", "1000/minute")):
        monkeypatch.setattr(ratelimit, name, parse(rate))
    ratelimit.reset()
    return TestClient(main.app, raise_server_exceptions=False)


def test_balance_endpoint_saves_a_version_and_repeating_it_is_free(api):
    r = api.post("/api/plan/lagos-creators/balance")
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert v2["version"] == 2 and v2["coverage"]["covered"] > example("lagos-creators").coverage.covered
    calls = main.llm.structured_calls
    again = api.post("/api/plan/lagos-creators/balance")
    assert again.json()["plan_id"] == v2["plan_id"] and main.llm.structured_calls == calls
    assert api.get(f"/api/plan/{v2['plan_id']}").json()["coverage"]["covered"] == v2["coverage"]["covered"]
    versions = api.get(f"/api/plan/{v2['plan_id']}/versions").json()["versions"]
    assert [v["version"] for v in versions] == [1, 2] and versions[1]["instruction"] == "Balance the lineup"
    # nothing left to balance: a friendly error, not a crash
    nothing = api.post(f"/api/plan/{v2['plan_id']}/balance")
    assert nothing.status_code == 422 and "Nothing to balance" in nothing.json()["error"]


def test_balance_unknown_plan_and_rate_limit(api, monkeypatch):
    assert api.post("/api/plan/doesnotexist/balance").status_code == 404
    monkeypatch.setattr(ratelimit, "_item", parse("1/hour")); ratelimit.reset()
    assert api.post("/api/plan/pixel-pact/balance").status_code == 200
    assert api.post("/api/plan/sunrise-run-club/balance").status_code == 429
