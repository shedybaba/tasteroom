"""Coverage (who has a pick made for them) with personal picks, and "Balance the lineup" (moves personal picks into the lineup)."""
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from limits import parse

from app import coverage, main, personal, ratelimit, refine
from app.brief import DOMAIN_FIELD
from app.models import Contribution, PersonalSkip, PlanResponse
from app.tools import PlanError
from tests.fakes import FakeLLM

run = asyncio.run
PRECOMPUTED = Path(__file__).resolve().parents[1] / "precomputed"
EXAMPLES = ("lagos-creators", "pixel-pact", "sunrise-run-club")


def example(eid: str) -> PlanResponse:
    return PlanResponse.model_validate(json.loads((PRECOMPUTED / f"{eid}.json").read_text())["plan"])


def standout_only(plan: PlanResponse) -> PlanResponse:
    """The same plan as if personal picks did not exist (the strict rule on its own)."""
    return plan.model_copy(update={"personal": [], "personal_skipped": []})


class Offline:
    mock = False


def strength(plan: PlanResponse, entity_id: str, member: str) -> float:
    for recs in plan.recommendations.values():
        for r in recs:
            if r.entity.id == entity_id:
                return next((c.score for c in r.why if c.member == member), 0.0) * len(r.why)
    raise AssertionError(f"{entity_id} is not a group result in this plan")


def brief_ids(plan: PlanResponse) -> set[str]:
    return {p.entity_id for f in DOMAIN_FIELD.values() for p in getattr(plan.brief, f)}


# ---- the strict "stands out" rule is unchanged -----------------------------------------------------------------------

@pytest.mark.parametrize("eid", EXAMPLES)
def test_the_standout_count_still_uses_the_strict_ui_threshold(eid):
    plan = example(eid)
    cov = plan.coverage
    by_hand = 0
    for m in plan.request.members:
        mine = [i for i in brief_ids(plan) if i in {r.entity.id for rs in plan.recommendations.values() for r in rs} and strength(plan, i, m.name) >= 1.15]
        by_hand += bool(mine)
        row = next(r for r in cov.members if r.member == m.name)
        assert {p.entity_id for p in row.picks} == set(mine) and all(p.kind == "standout" and p.strength >= 1.15 for p in row.picks)
    assert cov.standout == by_hand


# ---- personal picks in the saved examples ----------------------------------------------------------------------------

@pytest.mark.parametrize("eid", EXAMPLES)
def test_every_member_has_a_personal_pick_or_a_stated_reason_and_the_headline_counts_both_kinds(eid):
    plan = example(eid)
    cov, members = plan.coverage, [m.name for m in plan.request.members]
    have = {p.member for p in plan.personal}
    for m in members:                                                 # never hidden: a pick, or a reason
        assert m in have or any(s.member == m for s in plan.personal_skipped), f"{m} has neither a personal pick nor a reason"
    assert cov.personal == len(have) and cov.covered == len(have | {r.member for r in cov.members if r.picks}) and cov.total == len(members)
    assert cov.standout <= cov.covered <= cov.total and cov.in_lineup <= cov.covered


@pytest.mark.parametrize("eid", EXAMPLES)
def test_personal_picks_are_discoveries_that_fit_the_group_and_are_explained_from_data(eid):
    plan = example(eid)
    named = {r.entity.id for r in plan.resolved if r.entity}
    seen = set()
    for p in plan.personal:
        assert p.entity.id not in named                                        # never something a member already said
        assert (p.member, p.domain) not in seen; seen.add((p.member, p.domain))   # one per member per domain
        assert p.member_rank >= 1 and p.member in p.explanation and f"#{p.member_rank}" in p.explanation
        group = [r.entity.id for r in plan.recommendations[p.domain]]
        if p.fit == "in_group_results":
            assert p.entity.id in group and p.group_rank == group.index(p.entity.id) + 1
        else:
            assert p.entity.id not in group and p.group_ratio is not None and p.group_ratio >= personal.GROUP_FIT_RATIO


def test_a_member_with_no_personal_pick_in_a_domain_still_gets_one_from_another_when_available():
    plan = example("pixel-pact")
    music = {p.member for p in plan.personal if p.domain == "music"}
    skipped_music = {s.member for s in plan.personal_skipped if s.domain == "music"}
    assert skipped_music, "pixel-pact has members whose music results do not fit the group"
    for m in skipped_music:
        assert m in {p.member for p in plan.personal if p.domain == "content"} or any(s.member == m and s.domain == "content" for s in plan.personal_skipped)
        assert m not in music


# ---- the standout-only paths (members with no personal pick) ---------------------------------------------------------

def test_a_member_with_nothing_is_told_why_and_no_swap_is_invented():
    plan = example("pixel-pact")
    bare = plan.model_copy(update={"personal": [p for p in plan.personal if p.member != "Kai"],
                                   "personal_skipped": [PersonalSkip(member="Kai", domain="music", reason="none_fit_group", note="too far from the group")]})
    row = next(r for r in bare.coverage.members if r.member == "Kai")
    assert not row.covered and row.note == "too far from the group" and row.suggestion is None and row.personal is None


def test_without_personal_picks_a_standout_result_is_still_used_for_members_it_stands_out_for():
    plan = standout_only(example("lagos-creators"))
    swaps = plan.coverage.balance
    assert swaps, "lagos has members for whom a real result stands out"
    in_brief = brief_ids(plan)
    for s in swaps:
        assert s.add.kind == "standout" and s.add.entity_id not in in_brief and strength(plan, s.add.entity_id, s.member) >= 1.15


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
    old = json.loads(plan.model_dump_json()); old.pop("personal"); old.pop("personal_skipped")   # a plan saved before personal picks existed
    legacy = PlanResponse.model_validate(old)
    assert legacy.personal == [] and legacy.coverage.personal == 0


def test_a_single_contributor_has_no_even_share_so_it_is_never_a_standout():
    plan = standout_only(example("lagos-creators"))
    first = plan.recommendations["music"][0]
    solo = first.model_copy(update={"why": [Contribution(member="Ada", score=1.0, via=[])]})
    lone = plan.model_copy(update={"recommendations": {**plan.recommendations, "music": [solo] + plan.recommendations["music"][1:]}})
    assert all(solo.entity.id != p.entity_id for r in lone.coverage.members if r.member == "Ada" for p in r.picks)


# ---- Balance the lineup ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("eid", EXAMPLES)
def test_balance_only_promotes_a_members_own_personal_pick_and_keeps_every_rule(eid):
    plan = example(eid)
    cov = plan.coverage
    in_brief = brief_ids(plan)
    personal_ids = {(p.member, p.entity.id) for p in plan.personal}
    assert cov.balance, "each example has members whose personal pick is not in the lineup yet"
    for s in cov.balance:
        assert s.add.kind == "personal" and (s.member, s.add.entity_id) in personal_ids   # their own pick, never someone else's or a standout
        assert s.add.entity_id not in in_brief
        if s.drop:
            assert s.drop.entity_id in in_brief and s.drop.domain == s.add.domain
    assert {r.member: r.suggestion for r in cov.members if r.suggestion} == {s.member: s for s in cov.balance}   # rows promise what the button does
    child = run(refine.balance_plan(plan, Offline(), None))
    after = child.brief
    for d, cap in coverage.SECTION_CAP.items():
        ids = [p.entity_id for p in getattr(after, DOMAIN_FIELD[d])]
        mine = {p.entity.id for p in plan.personal}
        assert len(ids) <= cap and (not ids or any(i not in mine for i in ids) or d in ("venues", "brands"))   # at least one crowd-pleaser stays


@pytest.mark.parametrize("eid", EXAMPLES)
def test_balance_puts_members_in_the_lineup_without_uncovering_anyone_or_touching_the_headline_venue(eid):
    plan = example(eid)
    before = {r.member for r in plan.coverage.members if r.in_lineup}
    child = run(refine.balance_plan(plan, Offline(), None))
    after = {r.member for r in child.coverage.members if r.in_lineup}
    assert before < after and child.coverage.in_lineup > plan.coverage.in_lineup
    assert child.brief.venue[0].entity_id == plan.brief.venue[0].entity_id
    assert child.coverage.covered == plan.coverage.covered and child.personal == plan.personal      # nothing about personal picks changed
    assert child.recommendations == plan.recommendations                                           # existing results only


def test_pressing_balance_twice_changes_nothing_more_so_crowd_pleasers_always_stay():
    plan = example("pixel-pact")
    once = run(refine.balance_plan(plan, Offline(), None))
    assert once.coverage.balance == []                                           # idempotent: the limit counts personal picks already there
    with pytest.raises(PlanError, match="Nothing to balance"):
        run(refine.balance_plan(once, Offline(), None))


def test_balance_swaps_survive_a_brief_writer_that_drops_them_and_it_uses_one_writer_call():
    plan = example("lagos-creators")
    llm = FakeLLM()                       # its brief keeps only the first pick per section: the swaps must survive that
    child = run(refine.balance_plan(plan, Offline(), llm))
    wanted = {s.add.entity_id for s in plan.coverage.balance}
    assert wanted <= brief_ids(child)
    assert llm.structured_calls == 1
    assert child.parent_id == plan.plan_id and child.version == 2 and child.refinement.instruction == "Balance the lineup"
    assert child.trace[-1].tool == "balance_lineup" and child.refinement.trace_start == len(plan.trace)


def test_a_promoted_personal_pick_reads_as_personal_not_as_a_crowd_pleaser():
    plan = example("lagos-creators")
    child = run(refine.balance_plan(plan, Offline(), None))
    s = plan.coverage.balance[0]
    pick = next(p for f in DOMAIN_FIELD.values() for p in getattr(child.brief, f) if p.entity_id == s.add.entity_id)
    assert s.member in pick.reason and "crowd-pleaser" not in pick.reason and "fits all 1 members" not in pick.reason


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(main, "llm", FakeLLM())
    for name, rate in (("_item", "100/hour"), ("_read_item", "1000/minute")):
        monkeypatch.setattr(ratelimit, name, parse(rate))
    ratelimit.reset()
    return TestClient(main.app, raise_server_exceptions=False)


def test_balance_endpoint_saves_a_version_and_repeating_it_is_free(api):
    r = api.post("/api/plan/pixel-pact/balance")
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert v2["version"] == 2 and v2["coverage"]["in_lineup"] > example("pixel-pact").coverage.in_lineup and len(v2["personal"]) == len(example("pixel-pact").personal)
    calls = main.llm.structured_calls
    again = api.post("/api/plan/pixel-pact/balance")
    assert again.json()["plan_id"] == v2["plan_id"] and main.llm.structured_calls == calls
    assert api.get(f"/api/plan/{v2['plan_id']}").json()["coverage"]["in_lineup"] == v2["coverage"]["in_lineup"]
    versions = api.get(f"/api/plan/{v2['plan_id']}/versions").json()["versions"]
    assert [v["version"] for v in versions] == [1, 2] and versions[1]["instruction"] == "Balance the lineup"
    nothing = api.post(f"/api/plan/{v2['plan_id']}/balance")                     # nothing left to balance: a friendly error, not a crash
    assert nothing.status_code == 422 and "Nothing to balance" in nothing.json()["error"]


def test_balance_unknown_plan_and_rate_limit(api, monkeypatch):
    assert api.post("/api/plan/doesnotexist/balance").status_code == 404
    monkeypatch.setattr(ratelimit, "_item", parse("1/hour")); ratelimit.reset()
    assert api.post("/api/plan/pixel-pact/balance").status_code == 200
    assert api.post("/api/plan/sunrise-run-club/balance").status_code == 429
