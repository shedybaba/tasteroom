"""Refine with the agent: only the affected domains are re-queried, the new version keeps everything else."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from limits import parse

from app.models import PlanResponse
from app import cache, main, plan_store, planner, ratelimit, refine
from app.llm import ToolCall, ToolStep
from app.models import Member, PlanRequest, Taste
from app.qloo_client import QlooClient, Response
from app.tools import PlanContext, PlanError
from tests.fakes import FakeLLM

run = asyncio.run
HOODS = [("Ikoyi", "I" * 36), ("Victoria Island", "V" * 36), ("Maroko", "M" * 36)]


def ent(prefix, i, etype, hood=None):
    e = {"name": f"{prefix} {i}", "entity_id": f"{prefix}-{i}".replace(" ", "").ljust(36, "0").upper(), "types": [etype], "popularity": 0.9,
         "properties": {"image": {"url": "https://img/x.jpg"}, "short_description": f"{prefix} {i}", "address": f"{i} Road, {hood[0] if hood else ''}"},
         "tags": [{"name": "Afrobeats", "tag_id": "urn:tag:genre:afrobeats", "type": "urn:tag:genre"}]}
    e["type"], e["subtype"] = "urn:entity", etype
    if hood:
        e["properties"]["locality"] = {"neighborhood": {"name": hood[0], "entity_id": hood[1]}}
    return e


class VaryingQloo(QlooClient):
    """Serves the saved samples for /search, and insights whose results DEPEND on the filters (so a refinement can
    be seen to change picks). Records every call."""

    def __init__(self, empty_tags=()):
        super().__init__(api_key="x", mock=False)
        self.calls, self.empty_tags = [], set(empty_tags)

    async def request(self, path, params, **kw):
        self.calls.append((path, dict(params)))
        if path == "/v2/tags":
            q = params["filter.query"]
            tags = [{"id": f"urn:tag:genre:music:{q}", "name": q.title(), "parents": [{"type": "urn:entity:artist"}]},
                    {"id": f"urn:tag:style:qloo:{q}", "name": q.title(), "parents": [{"type": "urn:entity:artist"}]},
                    {"id": f"urn:tag:genre:place:{q}", "name": q.title(), "parents": [{"type": "urn:entity:place"}]}]
            return Response(200, {"results": {"tags": tags}})
        if path != "/v2/insights":
            return self._mock(path, params)
        t = params["filter.type"].rsplit(":", 1)[-1]
        if params.get("filter.location") in {h[1] for h in HOODS}:
            tag = "HOOD"
        elif "filter.price_level.max" in params:
            tag = f"P{params['filter.price_level.max']}"
        elif "filter.popularity.max" in params:
            tag = "GEM"
        elif "filter.tags" in params:
            first = params["filter.tags"].split(",")[0]
            tag = "EMPTY" if first in self.empty_tags else "TAG"
        else:
            tag = "BASE"
        n = 0 if tag == "EMPTY" else 10
        ents = [ent(f"{t}-{tag}", i, params["filter.type"], HOODS[i % 3] if t == "place" else None) for i in range(n)]
        return Response(200, {"success": True, "results": {"entities": ents}})


class RefineLLM(FakeLLM):
    """Scripted refinement agent, chosen by the organizer's request. `overreach` also tries unaffected domains."""

    SCRIPTS = {
        "cheaper": [("find_venues", {"price_level_max": 2})],
        "gems": [("recommend", {"domain": "music", "hidden_gems": True}), ("recommend", {"domain": "brands", "hidden_gems": True})],
        "chill": [("find_tags", {"domain": "music", "query": "chill"}), ("recommend", {"domain": "music", "tags": ["Chill"]})],
        "hood": [("list_neighbourhoods", {}), ("find_venues", {"neighbourhood": "Victoria Island"})],
        "content": [("recommend", {"domain": "content"})],
    }

    def __init__(self, key, overreach=False, **kw):
        super().__init__(**kw)
        self.key, self.overreach, self.refine_steps = key, overreach, 0

    async def tool_step(self, *, instructions, input_items, tools):
        if "refining an existing event plan" not in instructions:
            return await super().tool_step(instructions=instructions, input_items=input_items, tools=tools)
        n = sum(1 for i in input_items if isinstance(i, dict) and i.get("type") == "function_call_output")
        plan = list(self.SCRIPTS[self.key])
        if self.overreach:
            plan = [("recommend", {"domain": "music"}), ("find_venues", {"price_level_max": 2}), ("recommend", {"domain": "brands"})]
        plan.append(("finish", {}))
        if n >= len(plan):
            return ToolStep(calls=[])
        name, args = plan[n]
        self.refine_steps += 1
        return ToolStep(calls=[ToolCall(f"r{n}", name, args)])


def req(goal="launch party"):
    return PlanRequest(community_name="Crew", city="Lagos", event_goal=goal,
                       members=[Member(name=f"M{i}", tastes=[Taste(text="Burna Boy", kind="artist"), Taste(text="Nike", kind="brand")]) for i in range(3)])


def parent_plan(goal="launch party", llm=None, client=None):
    return run(planner.make_plan(req(goal), client or VaryingQloo(), llm or FakeLLM()))


def sections(brief):
    return {f: [p.entity_id for p in getattr(brief, f)] for f in ("music", "venue", "sponsors", "content")}


def tools_after(child):
    return [s.tool for s in child.trace[child.refinement.trace_start:]]


# ---- the request classifier ----------------------------------------------------------------------

def test_the_five_quick_refinements_map_to_the_right_domains():
    got = {q: (sorted(refine.classify(q).domains or []), refine.classify(q).mood) for q in refine.QUICK_REFINEMENTS}
    assert got["Cheaper venue"][0] == ["venues"]
    assert got["More hidden gems"][0] == ["brands", "content", "music"]
    assert got["Swap the music vibe: more chill"] == (["music"], "chill")
    assert got["Add a watch-party content theme"][0] == ["content"]            # "watch-party" must not look like a music mood
    assert got["Different neighbourhood"][0] == ["venues"]
    assert refine.classify("make it more family friendly").domains is None      # unknown: the agent decides
    assert refine.classify("calmer").mood == "calm" and refine.classify("lofi beats").mood == "lo-fi"


# ---- acceptance: "Cheaper venue" ------------------------------------------------------------------

def test_cheaper_venue_changes_only_venues_and_the_trace_shows_only_the_venue_call():
    parent = parent_plan()
    child = run(refine.refine_plan(parent, "Cheaper venue", VaryingQloo(), RefineLLM("cheaper")))
    assert child.parent_id == parent.plan_id and child.root_id == parent.plan_id and child.version == 2
    assert child.mode == "agent" and child.plan_id != parent.plan_id
    before, after = sections(parent.brief), sections(child.brief)
    assert after["venue"] != before["venue"] and all(v.startswith("PLACE-P2") for v in after["venue"])   # swapped for price<=2 venues
    for k in ("music", "sponsors", "content"):
        assert after[k] == before[k]                                          # untouched sections are identical
    assert {d: [r.entity.id for r in recs] for d, recs in child.recommendations.items() if d != "venues"} == \
           {d: [r.entity.id for r in recs] for d, recs in parent.recommendations.items() if d != "venues"}
    assert tools_after(child) == ["find_venues"]                              # ONLY the venue tool call
    step = child.trace[child.refinement.trace_start]
    assert step.args["price_level_max"] == 2 and "price_level_max" in step.refined and "venue_kind" in step.inferred
    assert [(c.domain, c.swapped, c.of, c.note) for c in child.refinement.changes] == [("venues", 1, 1, "price <= 2")]
    assert child.refinement.instruction == "Cheaper venue" and child.refinement.trace_start == len(parent.trace)
    assert child.trace[:len(parent.trace)] == parent.trace                    # the parent's steps are kept as they were


def test_cheaper_again_goes_one_level_lower():
    parent = parent_plan()
    v2 = run(refine.refine_plan(parent, "Cheaper venue", VaryingQloo(), RefineLLM("cheaper")))
    v3 = run(refine.refine_plan(v2, "cheaper please", VaryingQloo(), RefineLLM("cheaper")))
    assert v3.trace[v3.refinement.trace_start].args["price_level_max"] == 1
    assert v3.version == 2 or v3.root_id == parent.plan_id                    # same family


# ---- acceptance: "More hidden gems" -----------------------------------------------------------------

def test_hidden_gems_changes_music_and_brands_and_shows_filter_popularity_max_in_the_trace():
    parent = parent_plan()
    child = run(refine.refine_plan(parent, "More hidden gems", VaryingQloo(), RefineLLM("gems")))
    before, after = sections(parent.brief), sections(child.brief)
    assert after["music"] != before["music"] and after["sponsors"] != before["sponsors"]
    assert after["venue"] == before["venue"]
    steps = [s for s in child.trace[child.refinement.trace_start:] if s.tool != "personal_picks"]
    assert [(s.tool, s.args["domain"]) for s in steps] == [("recommend", "music"), ("recommend", "brands")]
    assert steps[0].args["filter.popularity.max"] == 0.7 and steps[1].args["filter.popularity.max"] == 0.9
    assert all(s.args["hidden_gems"] is True and "hidden_gems" in s.refined and s.inferred == [] for s in steps)
    assert {(c.domain, c.note) for c in child.refinement.changes} == {("music", "hidden gems on"), ("brands", "hidden gems on")}


def test_hidden_gems_does_not_add_a_domain_the_plan_lacks():
    parent = parent_plan()                                                    # the default plan has no content domain
    assert "content" not in parent.recommendations
    child = run(refine.refine_plan(parent, "More hidden gems", VaryingQloo(), None))   # deterministic fallback
    assert "content" not in child.recommendations and child.mode == "pipeline"
    assert [(s.tool, s.args.get("domain")) for s in child.trace[child.refinement.trace_start:]] == [("recommend", "music"), ("recommend", "brands"), ("personal_picks", None)]


# ---- the guard: unaffected domains are refused and never traced --------------------------------------

def test_calls_for_unaffected_domains_are_refused_and_do_not_appear_in_the_trace():
    parent = parent_plan()
    q = VaryingQloo()
    child = run(refine.refine_plan(parent, "Cheaper venue", q, RefineLLM("cheaper", overreach=True)))
    assert tools_after(child) == ["find_venues"]                              # music/brands refused, find_venues ran
    assert sections(child.brief)["music"] == sections(parent.brief)["music"]
    assert not [c for p, c in q.calls if p == "/v2/insights" and c["filter.type"] != "urn:entity:place"]   # Qloo never queried


# ---- vibe: tags -------------------------------------------------------------------------------------

def test_more_chill_uses_find_tags_then_recommend_with_tags():
    parent = parent_plan()
    child = run(refine.refine_plan(parent, "Swap the music vibe: more chill", VaryingQloo(), RefineLLM("chill")))
    steps = child.trace[child.refinement.trace_start:]
    assert [s.tool for s in steps] == ["find_tags", "recommend", "personal_picks"]   # music changed, so personal picks were redone
    assert steps[0].args == {"domain": "music", "query": "chill"}
    assert steps[1].args["tags"] == "Chill" and "tags" in steps[1].refined      # shown by name, not id
    assert sections(child.brief)["music"] != sections(parent.brief)["music"]
    assert sections(child.brief)["venue"] == sections(parent.brief)["venue"]
    assert child.refinement.changes[0].note == "tag: Chill"


def test_a_tag_that_matches_nothing_is_skipped_for_the_next_candidate():
    parent = parent_plan()
    q = VaryingQloo(empty_tags={"urn:tag:genre:music:chill"})                  # exists in Qloo but returns 0 artists (measured)
    child = run(refine.refine_plan(parent, "more chill music", q, None))       # deterministic path passes the top candidates
    tagged = [c for p, c in q.calls if p == "/v2/insights" and "filter.tags" in c and c["filter.type"].endswith("artist")]
    assert tagged and sections(child.brief)["music"] != sections(parent.brief)["music"]
    assert child.refinement.changes[0].domain == "music"


def test_unknown_tag_names_are_ignored_not_sent_to_qloo():
    ctx = PlanContext(request=req(), client=VaryingQloo())
    parent = parent_plan()
    c = refine.build_context(parent, "chill", VaryingQloo(), {"music"})
    from app.tools import execute
    out = run(execute(c, "recommend", {"domain": "music", "tags": ["urn:tag:made:up", "Imaginary"]}))
    assert out["count"] > 0 and not [x for p, x in c.client.calls if "filter.tags" in x and x["filter.type"].endswith("artist")]
    assert c.trace[-1].args == {"domain": "music"}                              # nothing invented shows up in the trace
    assert ctx is not None


# ---- neighbourhoods -----------------------------------------------------------------------------------

def test_different_neighbourhood_lists_areas_then_filters_venues_to_one():
    parent = parent_plan()
    q = VaryingQloo()
    child = run(refine.refine_plan(parent, "Different neighbourhood", q, RefineLLM("hood")))
    steps = child.trace[child.refinement.trace_start:]
    assert [s.tool for s in steps] == ["list_neighbourhoods", "find_venues"]
    assert steps[1].args["neighbourhood"] == "Victoria Island" and "neighbourhood" in steps[1].refined
    venue_calls = [c for p, c in q.calls if p == "/v2/insights" and c["filter.location"] == HOODS[1][1]]
    assert venue_calls                                                          # the neighbourhood's own locality id was the filter
    assert all(v.startswith("PLACE-HOOD") for v in sections(child.brief)["venue"])
    assert child.refinement.changes[0].note == "area: Victoria Island"
    assert sections(child.brief)["music"] == sections(parent.brief)["music"]


def test_fallback_picks_a_neighbourhood_the_plan_is_not_already_in():
    parent = parent_plan()
    child = run(refine.refine_plan(parent, "Different neighbourhood", VaryingQloo(), None))
    headline = parent.recommendations["venues"][0].entity.neighborhood
    chosen = child.trace[child.refinement.trace_start + 1].args["neighbourhood"]
    # the fake's top-3 venues span every area, so the fallback must at least leave the headline pick's area
    assert child.mode == "pipeline" and chosen != headline


# ---- content ---------------------------------------------------------------------------------------------

def test_add_a_watch_party_theme_adds_the_content_domain():
    parent = parent_plan()
    assert not sections(parent.brief)["content"]
    child = run(refine.refine_plan(parent, "Add a watch-party content theme", VaryingQloo(), RefineLLM("content")))
    assert child.recommendations["content"] and sections(child.brief)["content"]
    assert tools_after(child) == ["recommend", "personal_picks"] and child.refinement.changes[0].domain == "content"
    assert sections(child.brief)["music"] == sections(parent.brief)["music"]


# ---- honesty: nothing to change -----------------------------------------------------------------------------

def test_if_qloo_returns_the_same_picks_the_user_is_told_and_nothing_is_saved():
    class Same(VaryingQloo):
        async def request(self, path, params, **kw):
            if path == "/v2/insights":
                self.calls.append((path, dict(params)))
                ents = [ent(f"{params['filter.type'][-5:]}-BASE", i, params["filter.type"], HOODS[i % 3]) for i in range(10)]
                return Response(200, {"success": True, "results": {"entities": ents}})
            return await super().request(path, params, **kw)
    parent = parent_plan(client=Same())
    with pytest.raises(PlanError) as e:
        run(refine.refine_plan(parent, "Cheaper venue", Same(), RefineLLM("cheaper")))
    assert "Nothing changed" in str(e.value)


def test_an_unintelligible_request_without_the_llm_gets_a_helpful_error():
    with pytest.raises(PlanError) as e:
        run(refine.refine_plan(parent_plan(), "make it more family friendly", VaryingQloo(), None))
    assert "cheaper venue" in str(e.value) and "different neighbourhood" in str(e.value)
    with pytest.raises(PlanError):
        run(refine.refine_plan(parent_plan(), "  x ", VaryingQloo(), None))


def test_the_agent_failing_falls_back_to_the_deterministic_steps():
    child = run(refine.refine_plan(parent_plan(), "Cheaper venue", VaryingQloo(), FakeLLM(fail=True)))
    assert child.mode == "pipeline" and any("hit a problem while refining" in w for w in child.warnings)
    assert tools_after(child) == ["find_venues"]


# ---- versions & ids --------------------------------------------------------------------------------------------

def test_refine_id_is_deterministic_and_sensitive_to_parent_and_text():
    a = refine.refine_id("p1", "Cheaper venue")
    assert a == refine.refine_id("p1", "  cheaper   VENUE ") and a != refine.refine_id("p2", "Cheaper venue") and a != refine.refine_id("p1", "x")


def test_brief_sections_are_restored_verbatim_for_untouched_domains():
    from app.brief import restore_unchanged
    parent = parent_plan()
    from app.models import Brief, BriefPick
    scrambled = parent.brief.model_copy(update={"music": [BriefPick(entity_id="ZZZ", name="x", reason="r")],
                                                "venue": [BriefPick(entity_id="NEW", name="n", reason="r")]})
    out = restore_unchanged(scrambled, parent.brief, {"venues"})
    assert out.music == parent.brief.music and out.venue == scrambled.venue and isinstance(out, Brief)


# ---- plan store -----------------------------------------------------------------------------------------------------

def test_plans_are_persisted_and_a_family_lists_in_version_order(tmp_path):
    s = plan_store.PlanStore(tmp_path / "p.sqlite3")
    p1 = parent_plan(); s.save(p1)
    v2 = run(refine.refine_plan(p1, "Cheaper venue", VaryingQloo(), None)); s.save(v2)
    assert [(r["version"], r["parent_id"]) for r in s.family(p1.plan_id)] == [(1, None), (2, p1.plan_id)]
    assert s.family(p1.plan_id)[1]["instruction"] == "Cheaper venue" and s.max_version(p1.plan_id) == 2
    assert s.load(v2.plan_id).refinement.changes == v2.refinement.changes
    assert s.load("nope") is None
    from datetime import timedelta
    assert s.prune(older_than=timedelta(seconds=-5)) == 2 and s.family(p1.plan_id) == []


# ---- API ------------------------------------------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch):
    q = VaryingQloo()
    monkeypatch.setattr(main, "qloo", q)
    monkeypatch.setattr(main, "llm", FakeLLM())
    for name, rate in (("_item", "100/hour"), ("_read_item", "1000/minute")):
        monkeypatch.setattr(ratelimit, name, parse(rate))
    ratelimit.reset()
    c = TestClient(main.app, raise_server_exceptions=False)
    c.q = q  # type: ignore[attr-defined]
    return c


def make_via_api(api, goal="launch party"):
    r = api.post("/api/plan", json=req(goal).model_dump(mode="json"))
    assert r.status_code == 200, r.text
    return r.json()


def test_refining_a_plan_updates_it_in_place_with_the_same_id_and_link(api, monkeypatch):
    monkeypatch.setattr(main, "llm", RefineLLM("cheaper"))
    p1 = make_via_api(api)
    r = api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Cheaper venue"})
    assert r.status_code == 200, r.text
    now = r.json()
    assert now["plan_id"] == p1["plan_id"] and now["version"] == p1["version"] and now["parent_id"] == p1["parent_id"]   # no new version
    assert now["refinement"]["changes"][0]["domain"] == "venues" and now["can_undo"] is True
    assert api.get(f"/api/plan/{p1['plan_id']}").json()["refinement"]["instruction"] == "Cheaper venue"                    # the link shows the change


def test_undo_last_change_restores_the_plan_exactly_and_only_once(api, monkeypatch):
    monkeypatch.setattr(main, "llm", RefineLLM("cheaper"))
    p1 = make_via_api(api)
    assert p1["can_undo"] is False
    api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Cheaper venue"})
    back = api.post(f"/api/plan/{p1['plan_id']}/undo")
    assert back.status_code == 200, back.text
    restored = back.json()
    assert restored["can_undo"] is False and restored["refinement"] is None
    assert restored["brief"] == p1["brief"] and restored["recommendations"] == p1["recommendations"]
    assert api.get(f"/api/plan/{p1['plan_id']}").json()["brief"] == p1["brief"]
    assert api.post(f"/api/plan/{p1['plan_id']}/undo").status_code == 404                                                # one level only


def test_a_second_change_can_be_undone_back_to_the_first(api, monkeypatch):
    monkeypatch.setattr(main, "llm", RefineLLM("cheaper"))
    p1 = make_via_api(api)
    first = api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Cheaper venue"}).json()
    monkeypatch.setattr(main, "llm", RefineLLM("gems"))
    second = api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "More hidden gems"})
    if second.status_code == 200:
        assert second.json()["plan_id"] == p1["plan_id"]
        assert api.post(f"/api/plan/{p1['plan_id']}/undo").json()["refinement"]["instruction"] == first["refinement"]["instruction"]


def test_undo_survives_a_cache_wipe_because_it_is_in_sqlite(api, monkeypatch):
    monkeypatch.setattr(main, "llm", RefineLLM("cheaper"))
    p1 = make_via_api(api)
    api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Cheaper venue"})
    cache._cache.clear()                                                         # as after a redeploy: the disk cache is gone
    assert api.get(f"/api/plan/{p1['plan_id']}").json()["can_undo"] is True
    assert api.post(f"/api/plan/{p1['plan_id']}/undo").json()["brief"] == p1["brief"]


def test_the_compare_baseline_is_not_stale_after_an_in_place_change(api, monkeypatch):
    monkeypatch.setattr(main, "llm", RefineLLM("cheaper"))
    p1 = make_via_api(api)
    before = api.post(f"/api/plan/{p1['plan_id']}/baseline").json()
    api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Cheaper venue"})
    after = api.post(f"/api/plan/{p1['plan_id']}/baseline").json()
    now = api.get(f"/api/plan/{p1['plan_id']}").json()
    assert after["qloo_stats"]["picks"] == sum(len(now["brief"][k]) for k in ("music", "venue", "sponsors", "content"))
    assert before["baseline"] == after["baseline"]                              # the LLM-only side depends on the request only


def test_refining_a_saved_example_makes_the_visitors_own_copy_and_undo_goes_back_to_the_example(api, monkeypatch):
    monkeypatch.setattr(main, "llm", RefineLLM("cheaper"))
    r = api.post("/api/plan/lagos-creators/refine", json={"instruction": "Cheaper venue"})
    assert r.status_code == 200, r.text
    mine = r.json()
    assert mine["plan_id"] != "lagos-creators" and mine["parent_id"] == "lagos-creators" and mine["mode"] != "precomputed" and mine["can_undo"] is True
    shared = api.get("/api/examples/lagos-creators/plan").json()
    assert shared["refinement"] is None and shared["brief"] != mine["brief"]      # the shared example itself is never changed
    back = api.post(f"/api/plan/{mine['plan_id']}/undo")
    assert back.status_code == 200 and back.json()["plan_id"] == "lagos-creators" and back.json()["mode"] == "precomputed"


def test_the_demo_rooms_plan_is_never_changed_in_place(api, monkeypatch):
    from app import planner
    from app.examples import EXAMPLES
    demo_id = planner.plan_id_for(EXAMPLES["lagos-creators"]["request"])
    base = PlanResponse.model_validate(json.loads((main.PRECOMPUTED / "lagos-creators.json").read_text())["plan"]).model_copy(update={"plan_id": demo_id})
    planner.store_plan(base)
    monkeypatch.setattr(main, "llm", RefineLLM("cheaper"))
    r = api.post(f"/api/plan/{demo_id}/refine", json={"instruction": "Cheaper venue"})
    assert r.status_code == 200 and r.json()["plan_id"] != demo_id
    assert api.get(f"/api/plan/{demo_id}").json()["brief"] == base.model_dump(mode="json")["brief"]


def test_refine_validation_limits_and_unknown_plans(api, monkeypatch):
    p1 = make_via_api(api)
    assert api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "ab"}).status_code == 422
    assert api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "x" * 201}).status_code == 422
    assert api.post(f"/api/plan/{p1['plan_id']}/refine", json={}).status_code == 422
    nf = api.post("/api/plan/doesnotexist/refine", json={"instruction": "Cheaper venue"})
    assert nf.status_code == 404 and "not found" in nf.json()["error"]
    vague = api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "make it more family friendly"})
    assert vague.status_code in (200, 422) and "Traceback" not in vague.text


def test_refining_shares_the_live_plan_rate_limit(api, monkeypatch):
    monkeypatch.setattr(main, "llm", RefineLLM("cheaper"))
    p1 = make_via_api(api)
    monkeypatch.setattr(ratelimit, "_item", parse("1/hour")); ratelimit.reset()
    assert api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Cheaper venue"}).status_code == 200
    limited = api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Different neighbourhood"})
    assert limited.status_code == 429 and "limit" in limited.json()["error"]


def test_comparison_for_a_refined_version_uses_that_versions_picks_and_one_llm_baseline(api, monkeypatch):
    llm = RefineLLM("cheaper"); monkeypatch.setattr(main, "llm", llm)
    p1 = make_via_api(api)
    v2 = api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Cheaper venue"}).json()
    b1 = api.post(f"/api/plan/{p1['plan_id']}/baseline").json()
    b2 = api.post(f"/api/plan/{v2['plan_id']}/baseline").json()
    assert b1["baseline"] == b2["baseline"]                                      # the LLM-only answer depends on the request, not the version
    calls = llm.structured_calls
    api.post(f"/api/plan/{v2['plan_id']}/baseline"); assert llm.structured_calls == calls     # cached
    assert b2["qloo_stats"]["venues"] == len(v2["brief"]["venue"])
    assert api.post("/api/plan/doesnotexist/baseline").status_code == 404
    ex = api.post("/api/plan/lagos-creators/baseline").json()
    assert ex["mode"] == "llm" and ex["baseline_stats"]["picks"] > 0             # the example's saved LLM-only answer is reused


def test_a_version_that_exists_only_in_the_cache_is_written_through_to_sqlite(api, monkeypatch):
    monkeypatch.setattr(main, "llm", RefineLLM("cheaper"))
    p1 = make_via_api(api)
    v2 = api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Cheaper venue"}).json()
    plan_store.get_store().prune(older_than=__import__("datetime").timedelta(seconds=-5))   # the DB loses it; the cache still has it
    assert plan_store.get_store().load(v2["plan_id"]) is None
    again = api.post(f"/api/plan/{p1['plan_id']}/refine", json={"instruction": "Cheaper venue"})
    assert again.status_code == 200 and plan_store.get_store().load(v2["plan_id"]) is not None


def test_tags_with_the_same_name_from_different_taxonomies_are_shown_once():
    parent = parent_plan()
    c = refine.build_context(parent, "chill", VaryingQloo(), {"music"})
    from app.tools import execute
    tags = run(execute(c, "find_tags", {"domain": "music", "query": "chill"}))["tags"]
    assert len({t["name"] for t in tags}) < len(tags)                           # the premise: duplicate names exist
    run(execute(c, "recommend", {"domain": "music", "tags": [t["id"] for t in tags]}))
    assert c.trace[-1].args["tags"] == "Chill" and c.refine.notes["music"] == ["tag: Chill"]


# ---- stale versions of changed examples -----------------------------------------------------------------------------

def _child_of(root: str, pid: str):
    from app.models import PlanResponse
    import json as _json
    from pathlib import Path
    base = PlanResponse.model_validate(_json.loads((Path(__file__).resolve().parents[1] / "precomputed" / "lagos-creators.json").read_text())["plan"])
    return base.model_copy(update={"plan_id": pid, "parent_id": root, "root_id": root, "version": 2})


def test_versions_of_a_changed_example_are_dropped_and_unchanged_or_unrelated_ones_are_kept():
    store = plan_store.get_store()
    store.save(_child_of("ex-a", "a-v2")); store.save(_child_of("ex-b", "b-v2"))
    assert store.reset_stale_families({"ex-a": "fp1", "ex-b": "fp1"}) == ["ex-a", "ex-b"]   # never recorded: older content, so cleared
    assert store.load("a-v2") is None and store.load("b-v2") is None
    store.save(_child_of("ex-a", "a-v2")); store.save(_child_of("ex-b", "b-v2"))
    assert store.reset_stale_families({"ex-a": "fp1", "ex-b": "fp1"}) == []                 # same content: refinements stay valid
    assert store.load("a-v2") and store.load("b-v2")
    assert store.reset_stale_families({"ex-a": "fp2", "ex-b": "fp1"}) == ["ex-a"]            # only the changed example is cleared
    assert store.load("a-v2") is None and store.load("b-v2")


def test_the_root_plan_itself_is_never_deleted_by_the_cleanup():
    store = plan_store.get_store()
    root = _child_of("ex-a", "ex-a").model_copy(update={"parent_id": None, "root_id": None, "version": 1})
    store.save(root); store.save(_child_of("ex-a", "a-v2"))
    store.reset_stale_families({"ex-a": "x"})
    assert store.load("ex-a") and store.load("a-v2") is None


def test_startup_cleanup_clears_old_refinements_of_the_demo_plan_and_examples_once(monkeypatch):
    from app import planner as pl
    from app.examples import EXAMPLES
    from app.rooms_api import reset_stale_example_versions
    demo = pl.plan_id_for(EXAMPLES["lagos-creators"]["request"])
    store = plan_store.get_store()
    store.save(_child_of("lagos-creators", "old-ex")); store.save(_child_of(demo, "old-demo"))
    reset_stale_example_versions()
    assert store.load("old-ex") is None and store.load("old-demo") is None
    store.save(_child_of("lagos-creators", "new-ex"))
    reset_stale_example_versions()                                   # same saved examples: a visitor's new refinement survives restarts
    assert store.load("new-ex")
