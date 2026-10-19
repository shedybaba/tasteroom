import asyncio

from fastapi.testclient import TestClient

from app import main
from app.models import Member, PlanOptions, Taste
from app.profile import build_profile
from app.qloo_client import QlooClient
from app.recommend import SIGNAL_TYPES, recommend, recommend_venues
from app.resolve import resolve_city, resolve_members


def setup():
    c = QlooClient(api_key="", mock=True)
    members = [Member(name="Ada", tastes=[Taste(text="Burna Boy", kind="artist"), Taste(text="Nike", kind="brand")])]
    prof = build_profile(asyncio.run(resolve_members(c, members)))
    return c, prof


class Spy(QlooClient):
    """Mock client that records insights params."""
    calls: list = []

    async def insights(self, params, **kw):
        self.calls.append(dict(params))
        return await super().insights(params, **kw)


def test_music_domain_returns_explained_recs_and_excludes_brands_from_signal():
    c, prof = setup()
    spy = Spy(api_key="", mock=True)
    spy.calls = []
    res = asyncio.run(recommend(spy, "music", prof))
    assert res.recommendations and all(r.why or r.shared_tags for r in res.recommendations)
    nike = next(i for i, pe in prof.entities.items() if pe.entity.type.endswith("brand"))
    assert nike not in spy.calls[0]["signal.interests.entities"]
    assert spy.calls[0]["feature.explainability"] is True
    assert "brand" not in SIGNAL_TYPES["music"] and SIGNAL_TYPES["brands"] == {"artist", "brand"}


def test_content_queries_podcast_and_tv_and_hidden_gems_flag():
    c, prof = setup()
    spy = Spy(api_key="", mock=True)
    spy.calls = []
    res = asyncio.run(recommend(spy, "content", prof, options=PlanOptions(hidden_gems=True)))
    assert {x["filter.type"] for x in spy.calls} == {"urn:entity:podcast", "urn:entity:tv_show"}
    assert all(x["filter.popularity.max"] == 0.7 for x in spy.calls)
    assert {r.entity.type for r in res.recommendations} == {"urn:entity:podcast", "urn:entity:tv_show"}


def test_venues_use_locality_id_and_options():
    c, prof = setup()
    spy = Spy(api_key="", mock=True)
    spy.calls = []
    loc = asyncio.run(resolve_city(c, "Lagos"))
    opts = PlanOptions(price_level_max=2, day="Saturday", venue_kind="bar")
    res = asyncio.run(recommend_venues(spy, prof, locality=loc, city="Lagos", options=opts))
    p = spy.calls[0]
    assert p["filter.location"] == loc.id and p["filter.price_level.max"] == 2 and p["filter.hours"] == "saturday"
    assert p["filter.tags"].startswith("urn:tag:")
    assert res.recommendations


def test_venues_fall_back_to_city_name_without_locality():
    c, prof = setup()
    spy = Spy(api_key="", mock=True)
    spy.calls = []
    res = asyncio.run(recommend_venues(spy, prof, locality=None, city="Lagos", options=PlanOptions()))
    assert spy.calls[0]["filter.location.query"] == "Lagos" and "filter.location" not in spy.calls[0]
    assert res.warnings
    none = asyncio.run(recommend_venues(spy, prof, locality=None, city="", options=PlanOptions()))
    assert none.recommendations == [] and none.warnings


def test_resolve_endpoint(monkeypatch):
    monkeypatch.setattr(main, "qloo", QlooClient(api_key="", mock=True))
    client = TestClient(main.app)
    r = client.post("/api/resolve", json={"city": "Lagos", "members": [
        {"name": "Ada", "tastes": [{"text": "Burna Boy", "kind": "artist"}, {"text": "Qwxzv Nope", "kind": "artist"}]}]})
    assert r.status_code == 200
    body = r.json()
    assert body["locality"]["name"] == "Lagos"
    assert body["resolved"][0]["entity"]["name"] == "Burna Boy" and body["resolved"][1]["entity"] is None
    assert client.post("/api/resolve", json={"city": "x"}).status_code == 422
