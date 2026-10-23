"""Coverage: who has a pick made for them, counting standout picks and personal picks apart."""
import asyncio
import json
from pathlib import Path

import pytest

from app import personal
from app.brief import DOMAIN_FIELD
from app.models import Contribution, PersonalSkip, PlanResponse

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

def test_a_member_with_nothing_is_told_why():
    plan = example("pixel-pact")
    bare = plan.model_copy(update={"personal": [p for p in plan.personal if p.member != "Kai"],
                                   "personal_skipped": [PersonalSkip(member="Kai", domain="music", reason="none_fit_group", note="too far from the group")]})
    row = next(r for r in bare.coverage.members if r.member == "Kai")
    assert not row.covered and row.note == "too far from the group" and row.personal is None


def test_members_with_no_matched_taste_are_not_counted_either_way():
    plan = example("lagos-creators")
    resolved = [r.model_copy(update={"entity": None}) if r.member == "Tunde" else r for r in plan.resolved]
    cov = plan.model_copy(update={"resolved": resolved}).coverage
    row = next(r for r in cov.members if r.member == "Tunde")
    assert not row.covered and "can't be measured" in row.note
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
