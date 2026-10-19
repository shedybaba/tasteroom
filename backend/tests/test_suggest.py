"""Guided taste input: /api/suggest, /api/ideas, and resolving tastes that carry an entity_id."""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from limits import parse

from app import main, qloo_client, ratelimit
from app.models import Member, SlimEntity, Taste
from app.qloo_client import QlooClient, QlooError, Response
from app.resolve import resolve_members
from app.suggest import STATIC_IDEAS, clean_query, ideas, suggest, to_suggestion

run = asyncio.run
UUID_A = "4A322BDD-04A3-4369-8234-B38A7FB485D9"
UUID_B = "C510E01A-E17C-45FC-8DCE-64A963A121A4"


def raw(name, id, type="urn:entity:artist", city=None, image="https://img/x.jpg"):
    props = {"image": {"url": image}, "short_description": f"{name} description " * 12}
    if city:
        props["geocode"] = {"city": city}
    return {"name": name, "entity_id": id, "types": [type], "properties": props, "popularity": 0.95,
            "tags": [{"name": "B2C", "tag_id": "urn:tag:g:b2c", "type": "urn:tag:genre"},
                     {"name": "Afrobeats", "tag_id": "urn:tag:genre:afrobeats", "type": "urn:tag:genre"}]}


class Recorder(QlooClient):
    """Mock-mode client that records every call and can serve scripted entities."""
    def __init__(self, search=None, insights=None, entities=None, fail=False):
        super().__init__(api_key="x", mock=False)
        self.calls, self._s, self._i, self._e, self._fail = [], search or [], insights or [], entities or {}, fail

    async def request(self, path, params, **kw):
        self.calls.append((path, dict(params)))
        if self._fail:
            return Response(503, {"message": "down"})
        if path == "/search":
            return Response(200, {"results": self._s})
        if path == "/v2/insights":
            batch = self._i(params) if callable(self._i) else self._i
            return Response(200, {"success": True, "results": {"entities": batch}})
        if path == "/entities":
            ids = params["entity_ids"].split(",")
            return Response(200, {"results": [self._e[i] for i in ids if i in self._e]})
        return Response(404, {})


# ---- suggest -----------------------------------------------------------------------------------

def test_suggestion_is_slim_and_tells_namesakes_apart():
    s = to_suggestion(SlimEntity(id="1", name="Burna Boy", type="urn:entity:artist", image="u", description="x " * 200,
                                 tags=["B2C", "Afrobeats"]))
    assert len(s.description) <= 112 and s.description.endswith("…") and s.subtitle == "Afrobeats"  # noise tag skipped
    p = to_suggestion(SlimEntity(id="2", name="Roma Lagos", type="urn:entity:place", city="Lagos", tags=["Bar"]))
    assert p.subtitle == "Lagos"


def test_suggest_maps_slots_to_qloo_types_and_requires_two_chars():
    c = Recorder(search=[raw("Burna Boy", UUID_A)])
    assert run(suggest(c, "b", "artist")) == [] and not c.calls
    out = run(suggest(c, "  bur  na ", "show"))
    assert out[0].name == "Burna Boy"
    path, params = c.calls[0]
    assert path == "/search" and params["query"] == "bur na" and params["types"] == "urn:entity:tv_show,urn:entity:movie"
    assert params["take"] == 6
    assert clean_query("a\x00b\n  c") == "a b c"


def test_suggest_floats_venues_in_the_organizers_city_to_the_top():
    results = [raw("Roma Pizza", "A" * 36, "urn:entity:place", city="Rome"), raw("Roma Lagos", "B" * 36, "urn:entity:place", city="Lagos"),
               raw("Roma Cafe", "C" * 36, "urn:entity:place", city="Paris")]
    c = Recorder(search=results)
    assert [s.name for s in run(suggest(c, "roma", "place", "Lagos"))][0] == "Roma Lagos"
    assert c.calls[0][1]["take"] == 15                                   # over-fetched for re-ranking
    c2 = Recorder(search=results)
    assert [s.name for s in run(suggest(c2, "roma", "place"))][0] == "Roma Pizza"  # no city: Qloo's order kept


def test_identical_lookups_hit_qloo_once():
    hits = []

    def handler(req):
        hits.append(1)
        return httpx.Response(200, json={"results": []})
    c = QlooClient(api_key="k", mock=False)
    c._http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://q.test")
    run(suggest(c, "burna", "artist")); run(suggest(c, "burna", "artist"))
    assert len(hits) == 1                                                # second one served from the 24 h cache


@pytest.fixture
def api(offline_client, monkeypatch):
    monkeypatch.setattr(main, "qloo", offline_client)
    monkeypatch.setattr(ratelimit, "_suggest_item", parse("5/minute"))
    ratelimit.reset()
    return TestClient(main.app, raise_server_exceptions=False)


def test_suggest_route_shape_and_validation(api):
    r = api.get("/api/suggest", params={"q": "burna", "type": "artist"})
    assert r.status_code == 200 and r.json()["results"][0]["name"] == "Burna Boy"
    assert set(r.json()["results"][0]) == {"id", "name", "type", "image", "description", "subtitle"}
    assert api.get("/api/suggest", params={"q": "b"}).status_code == 422
    assert api.get("/api/suggest", params={"q": "burna", "type": "weapon"}).status_code == 422
    assert api.get("/api/suggest", params={"q": "x" * 61}).status_code == 422
    bad = api.get("/api/suggest", params={"q": "b"}).json()
    assert "error" in bad and "fields" in bad                            # the friendly validation shape


def test_suggest_route_is_rate_limited_separately_from_plans(api):
    for _ in range(5):
        assert api.get("/api/suggest", params={"q": "burna"}).status_code == 200
    r = api.get("/api/suggest", params={"q": "burna"})
    assert r.status_code == 429 and "Pause a moment" in r.json()["error"]
    assert ratelimit.allow(type("R", (), {"headers": {}, "client": type("C", (), {"host": "1.1.1.1"})()})())  # plan bucket untouched


def test_suggest_route_degrades_when_qloo_is_down(api, monkeypatch):
    monkeypatch.setattr(main, "qloo", Recorder(fail=True))
    ratelimit.reset()
    r = api.get("/api/suggest", params={"q": "burna", "type": "artist"})
    assert r.status_code == 200 and r.json() == {"results": [], "unavailable": True}


# ---- ideas -------------------------------------------------------------------------------------

def test_ideas_use_popular_entities_with_no_taste_signal():
    c = Recorder(insights=[raw(f"Artist {i}", f"{i}" * 36) for i in range(8)])
    res = run(ideas(c, "artist"))
    path, params = c.calls[0]
    assert path == "/v2/insights" and params["filter.type"] == "urn:entity:artist"
    assert params["filter.popularity.min"] == "0.9" and params["take"] == "8" and "signal.interests.entities" not in params
    assert res.source == "qloo" and len(res.ideas) == 8 and all(i.id and i.image for i in res.ideas)


def test_show_ideas_mix_tv_and_movies():
    def by_type(p):
        t = p["filter.type"]
        return [raw(f"{t[-4:]}{i}", f"{'T' if 'tv' in t else 'M'}{i}".ljust(36, "0"), t) for i in range(8)]
    res = run(ideas(Recorder(insights=by_type), "show"))
    assert len(res.ideas) == 8 and {i.type for i in res.ideas} == {"urn:entity:tv_show", "urn:entity:movie"}
    assert [i.type for i in res.ideas[:2]] == ["urn:entity:tv_show", "urn:entity:movie"]  # alternating


def test_place_ideas_need_a_resolvable_city():
    c = Recorder(insights=[raw("X", "X" * 36, "urn:entity:place")])
    r = run(ideas(c, "place", ""))
    assert r.needs_city and r.ideas == [] and r.source == "none" and not c.calls   # world landmarks are useless: no call
    nowhere = Recorder(search=[])                                                  # city not found in Qloo
    assert run(ideas(nowhere, "place", "Zzyzx")).needs_city


def test_place_ideas_use_the_locality_hangout_tags_and_relax_popularity_for_small_cities():
    loc = {"name": "Lagos", "entity_id": "L" * 36, "types": ["urn:entity:locality"], "properties": {"akas": []}}
    seen = []

    def insights(p):
        seen.append(p)
        return [raw(f"Bar {i}", f"{i}" * 36, "urn:entity:place", city="Lagos") for i in range(2 if p["filter.popularity.min"] == "0.9" else 8)]
    c = Recorder(search=[loc], insights=insights)
    res = run(ideas(c, "place", "Lagos"))
    assert [p["filter.popularity.min"] for p in seen] == ["0.9", "0.7"]            # <4 results at 0.9, so it retried
    assert seen[0]["filter.location"] == "L" * 36 and "urn:tag:genre:place:lounge" in seen[0]["filter.tags"]
    assert len(res.ideas) == 8 and res.source == "qloo"


def test_ideas_fall_back_to_a_static_list_if_qloo_fails():
    res = run(ideas(Recorder(fail=True), "artist"))
    assert res.source == "static" and [i.name for i in res.ideas] == [n for n, _ in STATIC_IDEAS["artist"]]
    assert all(i.id is None for i in res.ideas)                                    # names only: resolved later
    assert run(ideas(Recorder(fail=True), "place", "Lagos")).ideas == []           # nothing sensible to fake for places


def test_ideas_route_validates_and_responds(api):
    r = api.get("/api/ideas", params={"type": "brand"})
    assert r.status_code == 200 and r.json()["type"] == "brand" and r.json()["ideas"]
    assert api.get("/api/ideas", params={"type": "any"}).status_code == 422       # only the five slot types
    assert api.get("/api/ideas", params={"type": "place"}).json()["needs_city"] is True


# ---- tastes carrying an entity_id ----------------------------------------------------------------

def member(*tastes):
    return Member(name="Ada", tastes=list(tastes))


def test_picked_entities_are_fetched_in_one_batch_without_searching():
    ents = {UUID_A: raw("Burna Boy", UUID_A), UUID_B: raw("Tems", UUID_B)}
    c = Recorder(entities=ents)
    out = run(resolve_members(c, [member(Taste(text="burna", kind="artist", entity_id=UUID_A.lower()),
                                          Taste(text="tems", kind="artist", entity_id=UUID_B))]))
    assert [r.entity.name for r in out] == ["Burna Boy", "Tems"] and not any(r.lookup_failed for r in out)
    assert [p for p, _ in c.calls] == ["/entities"]                                # one call, zero searches
    assert c.calls[0][1]["entity_ids"] == f"{UUID_A},{UUID_B}"                     # ids normalised and sorted


def test_unknown_picked_id_falls_back_to_a_text_search():
    c = Recorder(entities={}, search=[raw("Burna Boy", UUID_A)])
    out = run(resolve_members(c, [member(Taste(text="Burna Boy", kind="artist", entity_id=UUID_A))]))
    assert out[0].entity.name == "Burna Boy"
    assert [p for p, _ in c.calls] == ["/entities", "/search"]


def test_entity_batch_failure_degrades_to_search_and_big_batches_are_chunked():
    class Boom(Recorder):
        async def request(self, path, params, **kw):
            if path == "/entities":
                self.calls.append((path, params))
                return Response(500, {})
            return await super().request(path, params, **kw)
    c = Boom(search=[raw("Burna Boy", UUID_A)])
    out = run(resolve_members(c, [member(Taste(text="Burna Boy", kind="artist", entity_id=UUID_A))]))
    assert out[0].entity and out[0].entity.name == "Burna Boy"
    ids = [f"{i:036d}" for i in range(120)]
    c2 = Recorder(entities={i.upper(): raw(f"E{n}", i.upper()) for n, i in enumerate(ids)})
    run(resolve_members(c2, [member(*[Taste(text=f"e{n}", entity_id=i) for n, i in enumerate(ids[:6])])]
                        + [Member(name=f"M{k}", tastes=[Taste(text=f"x{n}", entity_id=i) for n, i in enumerate(ids[6 + k * 6:12 + k * 6])]) for k in range(19)]))
    batches = [p["entity_ids"].count(",") + 1 for path, p in c2.calls if path == "/entities"]
    assert batches == [50, 50, 20]                                                  # 120 distinct ids -> chunks of 50


def test_malformed_entity_ids_are_rejected_by_the_request_model():
    with pytest.raises(Exception):
        Taste(text="x", entity_id="'; DROP TABLE")
    assert Taste(text="x").entity_id is None and Taste(text="x", entity_id=UUID_A).entity_id == UUID_A
