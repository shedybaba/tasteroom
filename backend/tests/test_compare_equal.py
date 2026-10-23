"""The Compare tab is an equal comparison: the LLM-only plan has the same sections and the same number of picks per section as the
Qloo plan, and both sides are scored out of the same total."""
import asyncio
import json
from pathlib import Path

import pytest

from app import main
from app.baseline import fit_to_counts, llm_baseline, pick_counts, verify_baseline
from app.examples import EXAMPLES
from app.models import BaselineBrief, BaselinePick, Brief, BriefPick, Member, PlanRequest, Taste
from app.planner import make_plan
from tests.fakes import FakeLLM

run = asyncio.run
PRECOMPUTED = Path(__file__).resolve().parents[1] / "precomputed"
SECTIONS = ("music", "venue", "sponsors", "content")


def bp(n: int, prefix: str = "x") -> list[BaselinePick]:
    return [BaselinePick(name=f"{prefix}{i}", reason="r") for i in range(n)]


def baseline(music=0, venue=0, sponsors=0, content=0) -> BaselineBrief:
    return BaselineBrief(title="t", concept="c", vibe_words=["a"], run_of_show=["x"], promo_line="p",
                         music=bp(music, "m"), venue=bp(venue, "v"), sponsors=bp(sponsors, "s"), content=bp(content, "c"))


def request(goal="launch party", brand=True) -> PlanRequest:
    extra = [Taste(text="Nike", kind="brand")] if brand else []
    return PlanRequest(community_name="Lagos Creators", city="Lagos", event_goal=goal,
                       members=[Member(name=f"M{i}", tastes=[Taste(text="Burna Boy", kind="artist")] + extra) for i in range(3)])


def test_counts_come_from_the_plans_brief():
    brief = Brief(title="t", concept="c", vibe_words=[], run_of_show=[], promo_line="p",
                  music=[BriefPick(entity_id=str(i), name="m", reason="r") for i in range(3)],
                  venue=[BriefPick(entity_id=str(i), name="v", reason="r") for i in range(3)],
                  sponsors=[BriefPick(entity_id=str(i), name="s", reason="r") for i in range(2)], content=[])
    assert pick_counts(brief) == {"music": 3, "venue": 3, "sponsors": 2, "content": 0}


def test_extras_are_trimmed_and_a_section_the_plan_lacks_is_emptied():
    out = fit_to_counts(baseline(music=4, venue=3, sponsors=3, content=3), {"music": 3, "venue": 3, "sponsors": 2, "content": 0})
    assert [len(getattr(out, s)) for s in SECTIONS] == [3, 3, 2, 0]
    assert [p.name for p in out.music] == ["m0", "m1", "m2"]          # the first picks are kept, in order


def test_trimming_never_adds_picks():
    out = fit_to_counts(baseline(music=1, venue=1), {"music": 3, "venue": 3, "sponsors": 2, "content": 1})
    assert [len(getattr(out, s)) for s in SECTIONS] == [1, 1, 0, 0]


class Recorder(FakeLLM):
    """A FakeLLM that keeps the prompt it was given."""
    seen: dict = {}

    async def structured(self, *, instructions, user, schema, smart=True):
        if schema is BaselineBrief:
            self.seen = {"instructions": instructions, "user": json.loads(user)}
        return await super().structured(instructions=instructions, user=user, schema=schema, smart=smart)


def test_the_baseline_prompt_carries_the_counts_and_the_answer_is_trimmed_if_the_model_ignores_them():
    counts = {"music": 3, "venue": 3, "sponsors": 2, "content": 0}
    llm = Recorder(overshoot=2)                                         # asked for 3/3/2/0, answers 5/5/4/0
    out, mode = run(llm_baseline(request(), llm, counts))
    assert llm.seen["user"]["pick_counts"] == counts and "EXACTLY" in llm.seen["instructions"] and mode == "llm"
    assert [len(getattr(out, s)) for s in SECTIONS] == [3, 3, 2, 0]


def test_the_canned_mock_baseline_is_fitted_too():
    out, mode = run(llm_baseline(request(), None, {"music": 1, "venue": 1, "sponsors": 0, "content": 0}))
    assert mode == "mock" and [len(getattr(out, s)) for s in SECTIONS] == [1, 1, 0, 0]


def test_both_sides_are_scored_out_of_the_same_total_even_when_the_llm_gives_fewer_picks(offline_client):
    counts = {"music": 3, "venue": 3, "sponsors": 2, "content": 0}
    short = baseline(music=1, venue=1, sponsors=0, content=0)           # the model came up short
    stats = run(verify_baseline(offline_client, short, "Lagos", None, [], counts))
    assert stats.picks == 8 and stats.venues == 3                       # the plan's total, not the 2 picks it gave
    assert stats.verified_in_qloo <= 2 and stats.new_picks <= 2          # missing picks are misses, never "new" or "verified"


def test_a_live_comparison_has_the_plans_sections_and_picks(offline_client, monkeypatch):
    llm = FakeLLM(overshoot=2)
    plan = run(make_plan(request("Friends hangout", brand=True), offline_client, llm))      # personal event: no sponsors, no content
    monkeypatch.setattr(main, "llm", llm)
    monkeypatch.setattr(main, "qloo", offline_client)   # not the app-wide client: it is tied to the first test's event loop
    out = run(main._baseline_for(plan))
    want = pick_counts(plan.brief)
    assert want["sponsors"] == 0 and want["content"] == 0 and want["music"] > 0
    assert {s: len(getattr(out.baseline, s)) for s in SECTIONS} == want
    assert out.baseline_stats.picks == out.qloo_stats.picks == sum(want.values())
    assert out.baseline_stats.venues == out.qloo_stats.venues == want["venue"]


@pytest.mark.parametrize("eid", list(EXAMPLES))
def test_every_saved_example_compares_like_for_like(eid):
    saved = json.loads((PRECOMPUTED / f"{eid}.json").read_text())
    brief = saved["plan"]["brief"]
    got, want = saved["baseline"]["baseline"], {s: len(brief[s]) for s in SECTIONS}
    assert {s: len(got[s]) for s in SECTIONS} == want
    assert saved["baseline"]["baseline_stats"]["picks"] == saved["baseline"]["qloo_stats"]["picks"] == sum(want.values())
    assert saved["baseline"]["baseline_stats"]["venues"] == saved["baseline"]["qloo_stats"]["venues"] == want["venue"]
