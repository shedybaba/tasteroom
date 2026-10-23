"""A personal pick in the brief's lineup says who it was chosen for, in the BRIEF ROW text (not only on the card):
new plans, refinements, Markdown and the Discord post."""
import asyncio
import json
from pathlib import Path

import pytest

from app import attribution, discord
from app.brief import SECTIONS
from app.models import Brief, BriefPick, Contribution, PersonalPick, PlanResponse, Recommendation, SlimEntity

run = asyncio.run
PRECOMPUTED = Path(__file__).resolve().parents[1] / "precomputed"
EXAMPLES = ("lagos-creators", "pixel-pact", "sunrise-run-club")


def example(eid: str) -> PlanResponse:
    return PlanResponse.model_validate(json.loads((PRECOMPUTED / f"{eid}.json").read_text())["plan"])


def lineup_personal(plan: PlanResponse) -> list[tuple[PersonalPick, BriefPick]]:
    """Every (personal pick, its brief row) where the pick is in the main lineup."""
    rows = []
    for field, (domain, _cap) in SECTIONS.items():
        for row in getattr(plan.brief, field):
            rows += [(p, row) for p in plan.personal if p.domain == domain and p.entity.id == row.entity_id]
    return rows


def named_correctly(plan: PlanResponse) -> list[str]:
    """Problems with the brief rows of personal picks: the row must LEAD with the member it was chosen for."""
    bad = []
    for pick, row in lineup_personal(plan):
        if not row.reason.startswith("Personal pick for ") or pick.member not in row.reason.split(":", 1)[0]:
            bad.append(f"{pick.member}/{row.name}: {row.reason[:80]}")
    return bad


# ---- the three examples, as saved --------------------------------------------------------------------------------------

@pytest.mark.parametrize("eid", EXAMPLES)
def test_example_brief_rows_of_personal_picks_lead_with_the_member(eid):
    plan = example(eid)
    assert named_correctly(plan) == []


@pytest.mark.parametrize("eid", EXAMPLES)
def test_group_wording_never_replaces_the_member_and_only_says_what_the_group_data_supports(eid):
    plan = example(eid)
    child = plan
    group = {r.entity.id: r for recs in plan.recommendations.values() for r in recs}
    for pick, row in lineup_personal(child):
        head, _, rest = row.reason.partition(": ")
        assert pick.member in head                                    # the member is named before any group wording
        rec = group.get(pick.entity.id)
        n = len(rec.why) if rec else 0
        if "It also stands out for" in row.reason:
            who = row.reason.split("It also stands out for ")[1].rstrip(".").split(" and ")
            assert rec and n > 1 and all(next(c.score for c in rec.why if c.member == w) * n >= 1.15 for w in who)
            assert pick.member not in who
        if "crowd-pleaser" in row.reason:
            assert rec and n > 1 and f"fits all {n} members" in row.reason
            assert not any(c.score * n >= 1.15 for c in rec.why)      # nobody stands out, so "crowd-pleaser" is true
        if rec is None or n < 2:
            assert "stands out" not in row.reason and "crowd-pleaser" not in row.reason


# ---- the wording rules, on small hand-built data -----------------------------------------------------------------------

def ent(i: str, name: str) -> SlimEntity:
    return SlimEntity(id=i, name=name, type="urn:entity:artist")


def personal(member: str, i: str = "E1", rank: int = 1, via=("YOASOBI", "Jujutsu Kaisen"), fit="in_group_results", group_rank: int | None = 2) -> PersonalPick:
    return PersonalPick(member=member, domain="music", entity=ent(i, "Song"), via=list(via), member_rank=rank, fit=fit, group_rank=group_rank,
                        group_ratio=0.97, explanation="x")


def group_rec(scores: dict[str, float], i: str = "E1") -> Recommendation:
    return Recommendation(entity=ent(i, "Song"), domain="music", why=[Contribution(member=m, score=s, via=[]) for m, s in scores.items()],
                          shared_tags=[], explanation_method="qloo_explainability")


def test_reason_leads_with_the_member_their_tastes_and_the_group_fit_without_guessing_pronouns():
    text = attribution.personal_reason([personal("Priya")], None)
    assert text == ("Personal pick for Priya: Qloo's top match for their tastes (YOASOBI, Jujutsu Kaisen), "
                    "and it fits the group too: it is #2 in the group's music results.")


def test_a_lower_rank_is_stated_and_a_group_affinity_fit_says_so():
    text = attribution.personal_reason([personal("Kai", rank=4, via=(), fit="group_affinity", group_rank=None)], None)
    assert text.startswith("Personal pick for Kai: Qloo's #4 match for their tastes, and it fits the group too: Qloo ties it to the group at 97%")


def test_it_adds_who_else_it_stands_out_for_when_that_is_true():
    rec = group_rec({"Priya": 0.2, "Tessa": 0.5, "Omar": 0.3})              # even share 1/3: Tessa (1.5x) stands out, Omar (0.9x) not
    assert attribution.personal_reason([personal("Priya")], rec).endswith(" It also stands out for Tessa.")


def test_it_does_not_repeat_the_member_when_only_they_stand_out():
    rec = group_rec({"Priya": 0.6, "Tessa": 0.2, "Omar": 0.2})
    assert attribution.personal_reason([personal("Priya")], rec).endswith("results.")


def test_a_crowd_pleaser_is_stated_only_when_nobody_stands_out():
    rec = group_rec({"Priya": 0.34, "Tessa": 0.33, "Omar": 0.33})
    assert attribution.personal_reason([personal("Priya")], rec).endswith(" It is a crowd-pleaser: it fits all 3 members.")


def test_a_single_contributor_stand_in_is_not_group_data():
    assert attribution.group_sentence(group_rec({"Priya": 1.0}), ["Priya"]) is None


def test_two_members_who_got_the_same_result_are_both_named():
    text = attribution.personal_reason([personal("Ada", rank=1), personal("Bo", rank=3)], None)
    assert text.startswith("Personal pick for Ada and Bo: Qloo's top match for Ada's tastes (YOASOBI, Jujutsu Kaisen) and #3 match for Bo's tastes")


def test_attribute_rewrites_only_personal_rows_and_is_idempotent():
    brief = Brief(title="t", concept="c", vibe_words=["v"], run_of_show=["r"], promo_line="p", venue=[], sponsors=[], content=[],
                  music=[BriefPick(entity_id="E1", name="Song", reason="stands out for Tessa."), BriefPick(entity_id="E2", name="Other", reason="plain")])
    results = {"music": [group_rec({"Priya": 0.34, "Tessa": 0.33, "Omar": 0.33})]}
    once = attribution.attribute(brief, [personal("Priya")], results)
    assert once.music[0].reason.startswith("Personal pick for Priya:") and "stands out for Tessa." not in once.music[0].reason
    assert once.music[1].reason == "plain"
    assert attribution.attribute(once, [personal("Priya")], results) == once
    assert attribution.attribute(brief, [], results) == brief


# ---- everywhere the reason appears ----------------------------------------------------------------------------------

def test_the_discord_post_marks_artists_that_are_personal_picks():
    plan = example("lagos-creators")
    pick, row = next((p, r) for p, r in lineup_personal(plan) if p.domain == "music")
    plan = plan.model_copy(update={"brief": plan.brief.model_copy(update={"music": [row] + [r for r in plan.brief.music if r.entity_id != row.entity_id]})})
    artists = next(f for f in discord.announcement(plan, None)["embeds"][0]["fields"] if f["name"] == "Artists")["value"]
    assert f"• {row.name} (personal pick for {pick.member})" in artists
    others = [line for line in artists.splitlines() if row.name not in line]
    assert all("personal pick" not in line or any(q.member in line for q in plan.personal) for line in others)
