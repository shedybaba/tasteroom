import asyncio

import pytest
from fastapi.testclient import TestClient
from limits import parse

from app import main, ratelimit
from app.brief import templated_brief, validate_brief
from app.config import settings
from app.models import Brief, BriefPick, Member, PlanRequest, Taste
from app.planner import make_plan
from app.tools import PlanContext, PlanError, execute
from tests.fakes import FakeLLM

run = asyncio.run


def req(goal="launch party", n=3, tastes=("Burna Boy",)):  # only entities present in the saved samples
    return PlanRequest(
        community_name="Lagos Creators", city="Lagos", event_goal=goal,
        members=[Member(name=f"M{i}", tastes=[Taste(text=t, kind="artist") for t in tastes] + [Taste(text="Nike", kind="brand")])
                 for i in range(n)],
    )


# ---- agent / fallback --------------------------------------------------------------------------

def test_agent_plan_has_trace_and_valid_brief(offline_client):
    plan = run(make_plan(req(), offline_client, FakeLLM()))
    assert plan.mode == "agent" and not plan.warnings
    assert [t.tool for t in plan.trace][:2] == ["resolve_tastes", "recommend"]
    assert all(t.ok and t.ms >= 0 and t.summary for t in plan.trace) and [t.step for t in plan.trace] == list(range(1, len(plan.trace) + 1))
    assert plan.trace[2].args == {"venue_kind": "lounge", "day": "saturday"}
    assert plan.recommendations["music"] and plan.brief.music and plan.brief.venue


def test_agent_chooses_different_domains_for_different_goals(offline_client):
    party = run(make_plan(req("launch party"), offline_client, FakeLLM()))
    pod = run(make_plan(req("podcast listening meetup"), offline_client, FakeLLM()))
    assert set(party.recommendations) == {"music", "venues", "brands"}
    assert set(pod.recommendations) == {"content", "venues"}
    assert pod.brief.music == [] and pod.brief.content and pod.mode == "agent"


def test_fallback_when_agent_raises(offline_client):
    plan = run(make_plan(req(), offline_client, FakeLLM(fail=True)))
    assert plan.mode == "pipeline"
    assert set(plan.recommendations) == {"music", "venues", "brands", "content"}
    assert any("pipeline" in w for w in plan.warnings)
    assert plan.brief.music  # templated brief, because the fake's brief call fails too
    assert [t.tool for t in plan.trace][:3] == ["resolve_tastes", "resolve_city", "recommend"]


def test_agent_disabled_flag(offline_client, monkeypatch):
    monkeypatch.setattr(settings, "agent_disabled", True)
    llm = FakeLLM()
    plan = run(make_plan(req(), offline_client, llm))
    assert plan.mode == "pipeline" and not any("agent" in w.lower() for w in plan.warnings)
    assert set(plan.recommendations) == {"music", "venues", "brands", "content"}


def test_no_llm_runs_pipeline_with_templated_brief(offline_client):
    plan = run(make_plan(req(), offline_client, None))
    assert plan.mode == "pipeline" and plan.brief.title and plan.brief.venue


def test_mock_qloo_reports_mock_mode():
    from app.qloo_client import QlooClient
    assert run(make_plan(req(), QlooClient(api_key="", mock=True), None)).mode == "mock"


def test_incomplete_agent_is_topped_up_by_pipeline(offline_client):
    only_resolve = FakeLLM(scripts=lambda g: [("resolve_tastes", {}), ("finish", {})])
    plan = run(make_plan(req(), offline_client, only_resolve))
    assert plan.mode == "pipeline" and set(plan.recommendations) == {"music", "venues", "brands", "content"}
    assert plan.trace[0].tool == "resolve_tastes" and [t.tool for t in plan.trace].count("resolve_tastes") == 1  # work kept


def test_agent_tool_call_budget_is_ten(offline_client):
    ctx = PlanContext(request=req(), client=offline_client)
    from app.agent import run_agent
    assert run(run_agent(ctx, FakeLLM(loop_forever=True))) is False
    assert len(ctx.trace) == 10


def test_failed_tool_is_traced_not_raised(offline_client):
    ctx = PlanContext(request=req(), client=offline_client)
    out = run(execute(ctx, "no_such_tool", {}))
    assert "error" in out and ctx.trace[0].ok is False
    run(execute(ctx, "explain", {"domain": "music"}))  # nothing recommended yet
    assert ctx.trace[1].ok is False


def test_unmatched_tastes_give_friendly_plan_error(offline_client):
    bad = req(tastes=("Qwxzv Gibberish",))
    for m in bad.members:
        m.tastes = [Taste(text="Qwxzv Gibberish", kind="artist")]
    with pytest.raises(PlanError):
        run(make_plan(bad, offline_client, None))


# ---- grounding validator ----------------------------------------------------------------------

def test_validator_drops_invented_and_wrong_domain_picks(offline_client):
    llm = FakeLLM(cheat=True)
    plan = run(make_plan(req(), offline_client, llm))
    assert plan.dropped_picks == 2  # the invented artist + the music id used in the venue section
    ids = {r.entity.id for recs in plan.recommendations.values() for r in recs}
    for field in ("music", "venue", "sponsors", "content"):
        assert all(p.entity_id in ids for p in getattr(plan.brief, field))
    assert "Invented Artist" not in [p.name for p in plan.brief.music]
    assert all(p.name != "LLM spelling" for p in plan.brief.music)  # canonical Qloo name restored


def test_validator_fills_empty_sections_from_top_result(offline_client):
    ctx = PlanContext(request=req(), client=offline_client)
    run(execute(ctx, "resolve_tastes", {}))
    run(execute(ctx, "recommend", {"domain": "music"}))
    empty = Brief(title="t", concept="c", vibe_words=[], run_of_show=[], promo_line="p",
                  music=[BriefPick(entity_id="NOPE", name="Ghost", reason="r")], venue=[], sponsors=[], content=[])
    fixed, dropped = validate_brief(empty, ctx.results)
    assert dropped == 1 and fixed.music[0].entity_id == ctx.results["music"][0].entity.id
    assert fixed.music[0].reason and fixed.venue == []  # no venue results -> stays empty, nothing invented


def test_templated_brief_uses_only_qloo_names(offline_client):
    plan = run(make_plan(req(), offline_client, None))
    ids = {r.entity.id: r.entity.name for recs in plan.recommendations.values() for r in recs}
    for field in ("music", "venue", "sponsors", "content"):
        for p in getattr(plan.brief, field):
            assert ids[p.entity_id] == p.name and p.reason


# ---- API ---------------------------------------------------------------------------------------

@pytest.fixture
def api(offline_client, monkeypatch):
    monkeypatch.setattr(main, "qloo", offline_client)
    monkeypatch.setattr(main, "llm", FakeLLM())
    monkeypatch.setattr(ratelimit, "_item", parse("2/hour"))
    ratelimit.reset()
    return TestClient(main.app, raise_server_exceptions=False)


def body(goal="launch party"):
    return req(goal).model_dump(mode="json")


def test_plan_endpoint_cache_and_get(api):
    r = api.post("/api/plan", json=body())
    assert r.status_code == 200 and r.json()["mode"] == "agent"
    pid = r.json()["plan_id"]
    assert api.get(f"/api/plan/{pid}").json()["plan_id"] == pid
    assert api.get("/api/plan/doesnotexist").status_code == 404
    assert api.post("/api/plan", json=body()).json()["plan_id"] == pid  # cached


def test_rate_limit_counts_live_runs_only(api):
    assert api.post("/api/plan", json=body("launch party")).status_code == 200
    for _ in range(5):  # cache hits are free
        assert api.post("/api/plan", json=body("launch party")).status_code == 200
    assert api.post("/api/plan", json=body("podcast meetup")).status_code == 200
    r = api.post("/api/plan", json=body("chill hangout"))
    assert r.status_code == 429 and "limited" in r.json()["error"]


def test_validation_and_friendly_errors(api):
    assert api.post("/api/plan", json={**body(), "members": body()["members"][:2]}).status_code == 422  # min 3 members
    bad = body()
    for m in bad["members"]:
        m["tastes"] = [{"text": "Qwxzv Gibberish", "kind": "artist"}]
    r = api.post("/api/plan", json=bad)
    assert r.status_code == 422 and "error" in r.json() and "Traceback" not in r.text


def test_unexpected_error_is_friendly(api, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(main.planner, "make_plan", boom)
    r = api.post("/api/plan", json=body())
    assert r.status_code == 500 and "secret" not in r.text and "error" in r.json()


def test_baseline_endpoint_compares(api):
    r = api.post("/api/baseline", json=body())
    assert r.status_code == 200
    j = r.json()
    assert j["mode"] == "llm" and j["baseline"]["music"][0]["name"] == "Burna Boy"
    b, q = j["baseline_stats"], j["qloo_stats"]
    assert b["with_explanation"] == 0 and b["picks"] == 5
    assert b["verified_in_qloo"] < b["picks"]  # "Totally Made Up Band" is not in Qloo
    assert q["verified_in_qloo"] == q["picks"] == q["with_explanation"] > 0
    assert q["new_picks"] == q["picks"]                      # Qloo never recommends an input back
    assert b["new_picks"] < b["picks"]                       # the fake LLM echoes Burna Boy and Nike, which members named


def test_reason_text_keeps_member_and_tag_case(offline_client):
    from app.brief import reason_from_why
    from app.models import Contribution, Recommendation, SlimEntity
    rec = Recommendation(entity=SlimEntity(id="X", name="X", type="urn:entity:artist"), domain="music", explanation_method="qloo_explainability",
                         why=[Contribution(member="Chioma", score=0.4, via=["Rema", "TEms"]), Contribution(member="Ada", score=0.3, via=[]),
                              Contribution(member="Tunde", score=0.3, via=[])], shared_tags=["Afrobeats"])
    text = reason_from_why(rec)
    assert text.startswith("Stands out for Chioma (via Rema, TEms)") and "Afrobeats" in text


def test_vibe_words_skip_brand_noise(offline_client):
    plan = run(make_plan(req(), offline_client, None))
    assert not {v.lower() for v in plan.brief.vibe_words} & {"b2c", "b2b", "other"}


def test_brief_input_gives_fit_not_raw_member_scores(offline_client):
    import json
    from app.brief import brief_input, fit_phrase
    from app.models import Contribution, Recommendation, SlimEntity
    ctx = PlanContext(request=req(), client=offline_client)
    run(execute(ctx, "resolve_tastes", {}))
    run(execute(ctx, "recommend", {"domain": "music"}))
    row = json.loads(brief_input(ctx))["recommendations"]["music"][0]
    assert "fit" in row and "suits_members" not in row
    e = SlimEntity(id="X", name="X", type="urn:entity:artist")
    even = Recommendation(entity=e, domain="music", explanation_method="qloo_explainability",
                          why=[Contribution(member=m, score=1 / 3, via=[]) for m in "ABC"])
    assert fit_phrase(even) == "suits the whole group about equally (3 members)"
    top = Recommendation(entity=e, domain="music", explanation_method="qloo_explainability",
                         why=[Contribution(member="A", score=0.6, via=["Rema"]), Contribution(member="B", score=0.2, via=[]), Contribution(member="C", score=0.2, via=[])])
    assert fit_phrase(top) == "stands out for A (via Rema)"


def test_clean_pick_name_strips_roles_and_neighbourhoods():
    from app.baseline import clean_pick_name
    assert clean_pick_name("Top pick: Terra Kulture, Victoria Island") == ["Terra Kulture, Victoria Island", "Terra Kulture"]
    assert clean_pick_name("Dishoom King's Cross \u2014 backup") == ["Dishoom King's Cross"]
    assert clean_pick_name("Caravan King's Cross \u2014 top pick") == ["Caravan King's Cross"]
    assert clean_pick_name("Radisson Blu Hotel, Lagos Ikeja")[0] == "Radisson Blu Hotel, Lagos Ikeja"  # full name tried first
    assert clean_pick_name("Burna Boy") == ["Burna Boy"]


def test_unstated_day_and_price_filters_are_ignored(offline_client):
    from tests.fakes import FakeLLM  # noqa: F401
    r = req("launch party")  # no weekday, no budget in the goal or options
    ctx = PlanContext(request=r, client=offline_client)
    run(execute(ctx, "resolve_tastes", {}))
    run(execute(ctx, "find_venues", {"venue_kind": "bar", "day": "saturday", "price_level_max": 1}))
    step = ctx.trace[-1]
    assert step.ok and "ignored unstated day and price filter" in step.summary
    assert "saturday" not in step.summary and "price<=" not in step.summary


def test_stated_day_and_price_filters_are_honoured(offline_client):
    r = req("Saturday launch party on a tight budget")
    ctx = PlanContext(request=r, client=offline_client)
    run(execute(ctx, "resolve_tastes", {}))
    run(execute(ctx, "find_venues", {"day": "saturday", "price_level_max": 2}))
    s = ctx.trace[-1].summary
    assert "saturday" in s and "price<=2" in s and "ignored" not in s
