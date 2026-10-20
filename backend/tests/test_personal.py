"""Personal picks: a result found from ONE member's tastes that also fits the group (see app/personal.py)."""
import asyncio

import pytest

from app import personal
from app.models import Recommendation, ResolvedTaste, SlimEntity
from app.profile import build_profile
from app.qloo_client import InsightsResult, QlooError
from app.recommend import SIGNAL_TYPES

run = asyncio.run
ARTIST = "urn:entity:artist"
AVG = 0.94   # the group's average affinity in these tests


def ent(i: str, affinity=None, explain=None, etype=ARTIST) -> SlimEntity:
    return SlimEntity(id=i, name=f"Name {i}", type=etype, affinity=affinity, explain=explain or {}, tags=[], tag_ids=[])


def taste(member: str, i: str, etype=ARTIST) -> ResolvedTaste:
    return ResolvedTaste(member=member, input=f"in {i}", entity=ent(i, etype=etype))


class FakeQloo:
    """Answers three kinds of /v2/insights call: the group's (not made here), a member's own (signal = only their entities),
    and a group-affinity lookup (filter.results.entities). Records everything."""

    def __init__(self, member_lists: dict[str, list[str]], group_affinity: dict[str, float] | None = None, fail: set[str] = frozenset()):
        self.member_lists, self.group_aff, self.fail = member_lists, group_affinity or {}, fail
        self.calls: list[dict] = []
        self.inflight = self.max_inflight = 0
        self.mock = False

    async def insights(self, params, *, test_mode=False):
        self.calls.append(dict(params))
        self.inflight += 1; self.max_inflight = max(self.max_inflight, self.inflight)
        await asyncio.sleep(0.01)
        self.inflight -= 1
        sig = params["signal.interests.entities"]
        sig = sig if isinstance(sig, list) else sig.split(",")
        if "filter.results.entities" in params:
            ids = params["filter.results.entities"].split(",")
            return InsightsResult(entities=[ent(i, affinity=self.group_aff[i]) for i in ids if i in self.group_aff])
        key = sig[0]
        if key in self.fail:
            raise QlooError(429, "busy")
        return InsightsResult(entities=[ent(i, affinity=0.9, explain={e: 1 / len(sig) for e in sig}) for i in self.member_lists[key]])

    async def find_tags(self, *a, **k):
        return []


def group(*ids: str) -> list[Recommendation]:
    return [Recommendation(entity=ent(i, affinity=AVG), domain="music", why=[], shared_tags=[], explanation_method="tag_overlap") for i in ids]


def go(resolved, member_lists, group_ids, *, aff=None, fail=frozenset(), queries=None, domain="music"):
    members = list(dict.fromkeys(r.member for r in resolved))
    client = FakeQloo(member_lists, aff, fail)
    picks, skips = run(personal.compute(client, resolved, {domain: group(*group_ids)}, queries or {}, members))
    return client, {p.member: p for p in picks}, {s.member: s for s in skips}


def test_a_member_gets_their_highest_ranked_result_that_is_one_of_the_groups():
    resolved = [taste("Ada", "a1"), taste("Bo", "b1")]
    _, picks, skips = go(resolved, {"a1": ["x1", "G2", "G1"], "b1": ["G1", "x2"]}, ["G1", "G2", "G3"])
    assert picks["Ada"].entity.id == "G2" and picks["Ada"].member_rank == 2 and picks["Ada"].fit == "in_group_results" and picks["Ada"].group_rank == 2
    assert picks["Bo"].entity.id == "G1" and picks["Bo"].member_rank == 1 and not skips


def test_a_result_outside_the_group_list_counts_only_if_its_group_affinity_is_within_5_percent_of_the_average():
    resolved = [taste("Ada", "a1"), taste("Bo", "b1"), taste("Cy", "c1")]
    ok_aff, low_aff = AVG * 0.95, AVG * 0.949
    client, picks, skips = go(resolved, {"a1": ["near", "G1"], "b1": ["far", "unscored"], "c1": ["unscored", "far"]}, ["G1", "G2", "G3"],
                              aff={"near": ok_aff, "far": low_aff})
    assert picks["Ada"].entity.id == "near" and picks["Ada"].fit == "group_affinity" and picks["Ada"].group_ratio == pytest.approx(0.95, abs=0.001)
    assert "Bo" not in picks and skips["Bo"].reason == "none_fit_group"      # 0.949x is too far; an unscorable result is never guessed at
    assert "Cy" in skips
    lookups = [c for c in client.calls if "filter.results.entities" in c]
    assert len(lookups) == 1 and set(lookups[0]["filter.results.entities"].split(",")) == {"near", "far", "unscored"}


def test_entities_any_member_named_are_never_personal_picks():
    resolved = [taste("Ada", "a1"), taste("Bo", "b1")]
    _, picks, _ = go(resolved, {"a1": ["b1", "G1"], "b1": ["a1", "G2"]}, ["G1", "G2"])   # Qloo hands Ada the artist Bo named
    assert picks["Ada"].entity.id == "G1" and picks["Bo"].entity.id == "G2"


def test_each_member_is_queried_with_only_their_own_entities():
    resolved = [taste("Ada", "a1"), taste("Ada", "a2"), taste("Bo", "b1")]
    client, _, _ = go(resolved, {"a1": ["G1"], "b1": ["G1"]}, ["G1"])
    sigs = sorted(tuple(sorted(c["signal.interests.entities"])) for c in client.calls if "filter.results.entities" not in c)
    assert sigs == [("a1", "a2"), ("b1",)]


def test_a_pick_nobody_else_got_is_preferred_but_sharing_is_allowed_when_there_is_no_alternative():
    resolved = [taste("Ada", "a1"), taste("Bo", "b1"), taste("Cy", "c1")]
    _, picks, _ = go(resolved, {"a1": ["G1", "G2"], "b1": ["G1", "G3"], "c1": ["G1"]}, ["G1", "G2", "G3"])
    assert picks["Cy"].entity.id == "G1"                                   # Cy has no alternative, so Cy chooses first
    assert picks["Ada"].entity.id == "G2" and picks["Bo"].entity.id == "G3"
    resolved = [taste("Ada", "a1"), taste("Bo", "b1")]
    _, picks, _ = go(resolved, {"a1": ["G1"], "b1": ["G1"]}, ["G1"])
    assert picks["Ada"].entity.id == picks["Bo"].entity.id == "G1"         # only one candidate exists: shared, not dropped


def test_via_is_the_members_own_tastes_and_the_explanation_cites_them_and_the_group_fit():
    resolved = [taste("Ada", "a1"), taste("Bo", "b1")]
    _, picks, _ = go(resolved, {"a1": ["G2"], "b1": ["G1"]}, ["G1", "G2"])
    p = picks["Ada"]
    assert p.via == ["Name a1"]                                        # the member's own entity, as Qloo's explainability credits it
    assert "Ada's own tastes" in p.explanation and "#2 in the group's music results" in p.explanation and "Qloo's #1" in p.explanation


def test_skip_reasons_say_why_and_are_never_hidden():
    resolved = [taste("Ada", "a1"), taste("Bo", "brand1", etype="urn:entity:brand"), taste("Cy", "c1"), taste("Di", "d1")]
    _, picks, skips = go(resolved, {"a1": ["G1"], "c1": ["zzz"], "d1": ["G1"]}, ["G1", "G2"], fail={"d1"})
    assert set(picks) == {"Ada"}
    assert skips["Bo"].reason == "no_signal" and "give Qloo anything to work with" in skips["Bo"].note   # only a brand: no music signal
    assert skips["Cy"].reason == "none_fit_group" and "too far from the group" in skips["Cy"].note
    assert skips["Di"].reason == "qloo_error" and "busy" in skips["Di"].note


def test_queries_run_four_at_a_time_at_most():
    resolved = [taste(f"M{i}", f"e{i}") for i in range(12)]
    client, picks, _ = go(resolved, {f"e{i}": ["G1"] for i in range(12)}, ["G1"])
    assert client.max_inflight == personal.CONCURRENCY == 4 and len(picks) == 12


def test_a_member_query_uses_the_same_options_as_the_group_query():
    from app.models import PlanOptions
    resolved = [taste("Ada", "a1"), taste("Bo", "b1")]
    q = {"music": personal.DomainQuery(PlanOptions(hidden_gems=True))}
    client, _, _ = go(resolved, {"a1": ["G1"], "b1": ["G1"]}, ["G1"], queries=q)
    member_calls = [c for c in client.calls if "filter.results.entities" not in c]
    assert member_calls and all(c["filter.popularity.max"] == 0.7 for c in member_calls)


def test_run_never_raises_and_records_one_visible_trace_step():
    class Boom(FakeQloo):
        async def insights(self, params, **k):
            raise RuntimeError("boom")
    resolved = [taste("Ada", "a1")]
    trace: list = []
    # a failing Qloo call is a skip for that member, not an exception
    picks, skips = run(personal.run(Boom({}), resolved, {"music": group("G1")}, {}, ["Ada"], trace=trace))
    assert picks == [] and trace[-1].tool == "personal_picks"
    ok_trace: list = []
    picks, _ = run(personal.run(FakeQloo({"a1": ["G1"]}), resolved, {"music": group("G1")}, {}, ["Ada"], trace=ok_trace))
    assert len(picks) == 1 and ok_trace[0].ok and "1 of 1 members got a personal pick" in ok_trace[0].summary and ok_trace[0].args["domains"] == "music"


def test_a_domain_the_plan_does_not_have_is_not_computed():
    client = FakeQloo({"a1": ["G1"]})
    picks, skips = run(personal.compute(client, [taste("Ada", "a1")], {"venues": group("G1")}, {}, ["Ada"]))
    assert picks == [] and skips == [] and client.calls == []


# ---- through the real plan and refine paths ---------------------------------------------------------------------------

def _plan_helpers():
    from tests.test_refine import RefineLLM, VaryingQloo, parent_plan
    return RefineLLM, VaryingQloo, parent_plan


def test_a_built_plan_has_personal_picks_one_member_query_each_and_a_visible_trace_step():
    _, VaryingQloo, parent_plan = _plan_helpers()
    q = VaryingQloo()
    plan = parent_plan(client=q)
    members = [m.name for m in plan.request.members]
    assert plan.personal, "a plan with music results gets personal picks"
    assert {p.member for p in plan.personal} | {s.member for s in plan.personal_skipped} == set(members)   # nobody unaccounted for
    assert all(p.domain in ("music", "content") for p in plan.personal)
    assert plan.trace[-1].tool == "personal_picks" and plan.trace[-1].ok
    singles = [c for p, c in q.calls if p == "/v2/insights" and str(c.get("take")) == str(personal.MEMBER_TAKE)]   # recorded params are strings
    assert len(singles) == len(members)                                       # exactly one music query per member
    group_signal = next(c["signal.interests.entities"] for p, c in q.calls if p == "/v2/insights" and c["filter.type"].endswith("artist") and str(c["take"]) == "10")
    assert all(len(str(c["signal.interests.entities"]).split(",")) <= len(str(group_signal).split(",")) for c in singles)   # never wider than the group's own


def test_mock_data_gets_no_personal_picks_because_every_query_would_answer_the_same():
    from app import planner
    from tests.conftest import OfflineClient
    from tests.fakes import FakeLLM
    from tests.test_refine import req
    client = OfflineClient.make()
    client.mock = True
    plan = run(planner.make_plan(req(), client, FakeLLM()))
    assert plan.personal == [] and plan.personal_skipped == [] and not any(t.tool == "personal_picks" for t in plan.trace)


def test_a_venue_refinement_leaves_personal_picks_exactly_as_they_were_and_adds_no_trace_step():
    from app import refine
    RefineLLM, VaryingQloo, parent_plan = _plan_helpers()
    parent = parent_plan()
    child = run(refine.refine_plan(parent, "Cheaper venue", VaryingQloo(), RefineLLM("cheaper")))
    assert child.personal == parent.personal and child.personal_skipped == parent.personal_skipped
    assert [t.tool for t in child.trace[child.refinement.trace_start:]] == ["find_venues"]


def test_a_hidden_gems_refinement_recomputes_personal_picks_with_the_same_filter():
    from app import refine
    RefineLLM, VaryingQloo, parent_plan = _plan_helpers()
    parent = parent_plan()
    q = VaryingQloo()
    child = run(refine.refine_plan(parent, "More hidden gems", q, RefineLLM("gems")))
    member_calls = [c for p, c in q.calls if p == "/v2/insights" and str(c.get("take")) == str(personal.MEMBER_TAKE)]
    assert len(member_calls) == len(parent.request.members) and all(str(c["filter.popularity.max"]) == "0.7" for c in member_calls)   # members' queries got hidden gems too
    assert [t.tool for t in child.trace[child.refinement.trace_start:]].count("personal_picks") == 1
    assert {p.domain for p in child.personal} <= {"music", "content"} and child.personal
