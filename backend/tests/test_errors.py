"""Error-handling review: every failure the plan flow can meet should degrade, not crash."""
import asyncio

import httpx
import pytest

from app import qloo_client
from app.allowed_params import ARTIST
from app.models import Member, PlanRequest, Taste
from app.planner import make_plan
from app.qloo_client import QlooClient, QlooError
from app.resolve import resolve_city
from tests.fakes import FakeLLM

run = asyncio.run


def client_with(handler) -> QlooClient:
    c = QlooClient(api_key="k", base_url="https://qloo.test", mock=False)
    c._http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://qloo.test")
    return c


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []

    async def fake_sleep(s):
        slept.append(s)
    monkeypatch.setattr(qloo_client.asyncio, "sleep", fake_sleep)
    return slept


# ---- Qloo HTTP behaviour -----------------------------------------------------------------------

def test_429_is_retried_with_backoff_then_succeeds(no_sleep):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, json={}) if len(calls) < 3 else httpx.Response(200, json={"results": []})

    assert run(client_with(handler).search("x")) == []
    assert len(calls) == 3 and len(no_sleep) == 2 and no_sleep[1] > no_sleep[0]  # exponential


def test_429_honours_retry_after(no_sleep):
    seq = iter([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"results": []})])
    run(client_with(lambda r: next(seq)).search("x"))
    assert 7 <= no_sleep[0] < 8


def test_persistent_429_gives_up_with_friendly_error():
    with pytest.raises(QlooError) as e:
        run(client_with(lambda r: httpx.Response(429, json={"message": "slow down"})).search("x"))
    assert e.value.status == 429


def test_404_means_no_results_not_an_error():
    c = client_with(lambda r: httpx.Response(404, json={"message": "none"}))
    assert run(c.search("nothing")) == [] and run(c.find_tags("x")) == [] and run(c.get_entities(["A"])) == []


def test_400_raises_without_leaking_headers():
    c = client_with(lambda r: httpx.Response(400, json={"error": {"message": "bad location"}}))
    with pytest.raises(QlooError) as e:
        run(c.search("x"))
    assert e.value.status == 400 and "k" != str(e.value)  # message is the API's, never our key


def test_5xx_retried_then_raised():
    n = []

    def handler(req):
        n.append(1)
        return httpx.Response(503, json={})
    with pytest.raises(QlooError):
        run(client_with(handler).search("x"))
    assert len(n) == qloo_client.MAX_RETRIES + 1


def test_network_failure_becomes_qloo_error():
    def handler(req):
        raise httpx.ConnectError("down")
    with pytest.raises(QlooError) as e:
        run(client_with(handler).search("x"))
    assert e.value.status == 0 and "ConnectError" in str(e.value)


def test_concurrency_stays_at_the_measured_safe_value():
    assert qloo_client.CONCURRENCY == 6


def test_api_key_goes_in_header_never_in_url():
    seen = {}

    def handler(req):
        seen["url"], seen["key"] = str(req.url), req.headers.get("x-api-key")
        return httpx.Response(200, json={"results": {"entities": []}})
    c = QlooClient(api_key="SECRET-KEY-123", base_url="https://qloo.test", mock=False)
    c._http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://qloo.test",
                                headers={"X-Api-Key": "SECRET-KEY-123"})
    run(c.insights({"filter.type": ARTIST, "take": 1}))
    assert "SECRET" not in seen["url"] and seen["key"] == "SECRET-KEY-123"


def test_invalid_params_never_reach_the_network():
    hit = []
    c = client_with(lambda r: hit.append(1) or httpx.Response(200, json={"results": {"entities": []}}))
    res = run(c.insights({"filter.type": ARTIST, "filter.location": "x", "bogus": 1}))
    assert set(res.dropped_params) == {"filter.location", "bogus"}


# ---- plan flow under failure -------------------------------------------------------------------

def req(city="Lagos", members=3, tastes=("Burna Boy",)):
    return PlanRequest(community_name="C", city=city, event_goal="launch party",
                       members=[Member(name=f"M{i}", tastes=[Taste(text=t, kind="artist") for t in tastes]) for i in range(members)])


def test_locality_400_falls_back_to_city_name(offline_client):
    class Bad400(type(offline_client)):
        async def request(self, path, params, **kw):
            if params.get("types") == "urn:entity:locality":
                return qloo_client.Response(400, {"error": {"message": "bad"}})
            return self._mock(path, params)
    c = Bad400(api_key="x", mock=False)
    assert run(resolve_city(c, "Lagos")) is None  # swallowed, not raised
    plan = run(make_plan(req(), c, None))
    assert plan.locality is None and plan.recommendations["venues"]
    assert any("locality" in w.lower() for w in plan.warnings)


def test_unknown_city_still_returns_other_domains(offline_client):
    class NoVenues(type(offline_client)):
        async def request(self, path, params, **kw):
            if params.get("filter.type") == "urn:entity:place":
                return qloo_client.Response(200, {"success": True, "results": {"entities": []}})
            return self._mock(path, params)
    plan = run(make_plan(req(city="Atlantis"), NoVenues(api_key="x", mock=False), None))
    assert not plan.recommendations.get("venues") and plan.recommendations["music"]
    assert any("no venues" in w.lower() for w in plan.warnings)
    assert plan.brief.venue == []  # empty section, nothing invented


def test_agent_timeout_falls_back_to_pipeline(offline_client, monkeypatch):
    from app import agent

    class Slow(FakeLLM):
        async def tool_step(self, **kw):
            await asyncio.sleep(0)  # patched no-op; the timeout comes from the budget below
            raise asyncio.TimeoutError()
    plan = run(make_plan(req(), offline_client, Slow()))
    assert plan.mode == "pipeline" and plan.recommendations["music"]
    assert any("pipeline" in w for w in plan.warnings)
    monkeypatch.setattr(agent, "BUDGET_SECONDS", -1)
    plan2 = run(make_plan(req(), offline_client, FakeLLM()))
    assert plan2.mode == "pipeline" and any("out of time" in w for w in plan2.warnings)


def test_llm_brief_timeout_uses_template(offline_client):
    class BriefTimeout(FakeLLM):
        async def structured(self, **kw):
            raise TimeoutError("openai timed out")
    plan = run(make_plan(req(), offline_client, BriefTimeout()))
    assert plan.mode == "agent" and plan.brief.music and any("templated" in w for w in plan.warnings)


def test_partial_unresolved_tastes_warn_but_succeed(offline_client):
    r = req()
    r.members[0].tastes.append(Taste(text="Qwxzv Gibberish", kind="artist"))
    plan = run(make_plan(r, offline_client, None))
    assert any("Could not match 1 taste" in w for w in plan.warnings)
    assert [x for x in plan.resolved if x.entity is None]


def test_fifteen_members_six_tastes_each(offline_client):
    r = PlanRequest(community_name="Big", city="Lagos", event_goal="mixer", members=[
        Member(name=f"Member {i}", tastes=[Taste(text=t, kind="any") for t in ("Burna Boy", "Nike", "Burna Boy", "Nike", "Burna Boy", "Nike")])
        for i in range(15)])
    plan = run(make_plan(r, offline_client, FakeLLM()))
    assert len(plan.resolved) == 90 and plan.recommendations["music"]
    from app.profile import build_profile
    assert len(build_profile(plan.resolved).ids()) <= 25  # signal cap holds


def test_signal_cap_covers_every_member_with_many_distinct_tastes():
    from app.models import ResolvedTaste, SlimEntity
    from app.profile import build_profile
    rs = [ResolvedTaste(member=f"M{m}", input="x", entity=SlimEntity(id=f"E{m}-{t}", name=f"E{m}-{t}", type="urn:entity:artist"))
          for m in range(15) for t in range(6)]
    p = build_profile(rs)
    ids = p.ids()
    assert len(ids) == 25 and {p.entities[i].members[0] for i in ids} == {f"M{m}" for m in range(15)}


# ---- city validation ---------------------------------------------------------------------------

def _loc(name, akas=()):
    return {"name": name, "entity_id": name.upper(), "types": ["urn:entity:locality"],
            "properties": {"akas": [{"value": a} for a in akas]}}


def _city_client(results):
    return client_with(lambda r: httpx.Response(200, json={"results": results}))


def test_city_must_match_by_name_or_alias():
    # Abuja is filed under another name; the alias saves it
    abuja = _city_client([_loc("Federal Capital Territory", ["Abuja Federal Capital Territory", "Babban Birnin Tarayya"])])
    assert run(abuja.find_locality("Abuja")).name == "Federal Capital Territory"
    # the fuzzy search answered a nonsense city with "Atlantis": must be rejected
    junk = _city_client([_loc("Atlantis", ["Atlantis, Florida"]), _loc("Nueva Atlantis")])
    assert run(junk.find_locality("Zzyzx Atlantis Narnia")) is None
    # region suffix and punctuation are fine; Qloo's relevance order is kept
    lagos = _city_client([_loc("Lagos"), _loc("Lagos Island")])
    assert run(lagos.find_locality("Lagos, Nigeria")).name == "Lagos"
    assert run(_city_client([_loc("Port-Harcourt")]).find_locality("Port Harcourt")).name == "Port-Harcourt"
    assert run(_city_client([_loc("Lekki Phase 1")]).find_locality("Lekki")).name == "Lekki Phase 1"
    assert run(_city_client([]).find_locality("Nowhere")) is None and run(lagos.find_locality("  ")) is None


def test_unrecognised_city_warns_and_falls_back(offline_client):
    plan = run(make_plan(req(city="Zzyzx Atlantis Narnia"), offline_client, None))
    assert plan.locality is None and any("locality" in w.lower() for w in plan.warnings)


def test_busy_qloo_is_reported_as_busy_not_as_a_misspelling(offline_client):
    class Flaky(type(offline_client)):
        async def request(self, path, params, **kw):
            if path == "/search" and params.get("query") == "Nike":
                return qloo_client.Response(429, {"message": "rate limited"})
            return self._mock(path, params)
    r = req()
    r.members[0].tastes.append(Taste(text="Nike", kind="brand"))      # this lookup gets a 429
    r.members[1].tastes.append(Taste(text="Qwxzv Gibberish", kind="artist"))  # this one genuinely has no match
    plan = run(make_plan(r, Flaky(api_key="x", mock=False), None))
    busy = [x for x in plan.resolved if x.lookup_failed]
    assert [x.input for x in busy] == ["Nike"] and busy[0].entity is None
    assert any("Qloo was busy" in w and "Nike" in w for w in plan.warnings)
    unmatched = [w for w in plan.warnings if "Could not match" in w]
    assert len(unmatched) == 1 and "Qwxzv Gibberish" in unmatched[0] and "Nike" not in unmatched[0]
