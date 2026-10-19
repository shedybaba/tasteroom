"""Invite rooms: storage, safety rules, organizer auth, plan-from-room, demo room."""
import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient
from limits import parse

from app import main, planner, ratelimit, rooms
from app.models import Taste
from app.rooms import (DEMO_SLUG, DEMO_TOKEN, RoomError, RoomStore, StoredResponse, clean_member_name, clean_tastes,
                       hash_token, select_for_plan)
from app.rooms_api import seed_demo
from tests.fakes import FakeLLM
from tests.test_suggest import Recorder, raw

UUID_A = "4A322BDD-04A3-4369-8234-B38A7FB485D9"
UUID_B = "C510E01A-E17C-45FC-8DCE-64A963A121A4"


def make_store(tmp_path):
    return RoomStore(tmp_path / "x.sqlite3")


# ---- storage -----------------------------------------------------------------------------------

def test_token_is_stored_only_as_a_hash_and_checked_in_constant_time(tmp_path):
    s = make_store(tmp_path)
    room, token = s.create_room("Crew", "Lagos", "party")
    raw_col = sqlite3.connect(tmp_path / "x.sqlite3").execute("SELECT organizer_token FROM rooms").fetchone()[0]
    assert raw_col == hash_token(token) and token not in raw_col and len(raw_col) == 64
    assert s.check_token(room.slug, token) and not s.check_token(room.slug, token + "x")
    assert not s.check_token(room.slug, "") and not s.check_token("nosuchroom", token)


def test_slugs_are_unambiguous_unique_and_rooms_persist_across_restarts(tmp_path):
    s = make_store(tmp_path)
    slugs = {s.create_room("C", "L", "g")[0].slug for _ in range(50)}
    assert len(slugs) == 50 and all(len(x) == 8 and not set(x) & set("0o1li") for x in slugs)
    room, token = s.create_room("Persist", "Abuja", "meetup")
    s.add_response(room, "Ada", [{"text": "Burna Boy", "kind": "artist"}])
    again = RoomStore(tmp_path / "x.sqlite3")  # a new process opening the same file (a redeploy with a volume)
    assert again.get_room(room.slug).community_name == "Persist" and again.check_token(room.slug, token)
    assert [r.member_name for r in again.responses(room.id)] == ["Ada"]


def test_duplicate_names_are_rejected_case_insensitively_and_rooms_have_a_cap(tmp_path, monkeypatch):
    s = make_store(tmp_path)
    room, _ = s.create_room("C", "L", "g")
    s.add_response(room, "Ada", [{"text": "x", "kind": "any"}])
    with pytest.raises(RoomError) as e:
        s.add_response(room, "ADA", [{"text": "y", "kind": "any"}])   # the store gets already-cleaned names
    assert e.value.status == 409 and "already used that name" in e.value.message
    monkeypatch.setattr(rooms, "MAX_RESPONSES_PER_ROOM", 2)
    s.add_response(room, "Bo", [{"text": "x", "kind": "any"}])
    with pytest.raises(RoomError) as e:
        s.add_response(room, "Cy", [{"text": "x", "kind": "any"}])
    assert e.value.status == 409 and "full" in e.value.message


def test_member_names_are_first_names_or_nicknames_only():
    assert clean_member_name("  Big   Sam\n") == "Big Sam"
    for bad in ["", "   ", "ada@example.com", "https://x.co/me", "www.me.com", "visit me.com", "call 08012345678",
                "x" * 25]:
        with pytest.raises(RoomError):
            clean_member_name(bad)
    assert clean_member_name("Ada\x00\x07Obi") == "Ada Obi"            # control characters become spaces
    assert clean_member_name("Zoë") == "Zoë" and clean_member_name("Ngozi 2") == "Ngozi 2"


def test_tastes_are_trimmed_deduped_capped_and_need_at_least_one():
    t = lambda text, kind="any", eid=None: Taste(text=text, kind=kind, entity_id=eid)  # noqa: E731
    out = clean_tastes([t("  Burna   Boy "), t("burna boy"), t("Nike", "brand", UUID_A.lower()), t("   ")])
    assert [x["text"] for x in out] == ["Burna Boy", "Nike"] and out[1]["entity_id"] == UUID_A
    assert len(clean_tastes([t(f"T{i}") for i in range(6)])) == 6
    with pytest.raises(RoomError):
        clean_tastes([t("  "), t("\n")])


def resp(i, matched):
    return StoredResponse(i, f"M{i}", [{"text": "x", "kind": "any", **({"entity_id": "E"} if k < matched else {})} for k in range(3)], "t")


def test_selection_cap_keeps_the_best_matched_in_arrival_order():
    few = [resp(i, 0) for i in range(5)]
    assert select_for_plan(few) == (few, [])
    many = [resp(i, 3 if i % 4 else 0) for i in range(1, 21)]            # every 4th has no matched tastes
    used, left = select_for_plan(many)
    assert len(used) == 15 and len(left) == 5 and all(r.matched == 0 for r in left)
    assert [r.id for r in used] == sorted(r.id for r in used)             # chronological, not by score
    tie = [resp(i, 2) for i in range(1, 18)]
    assert [r.id for r in select_for_plan(tie)[1]] == [16, 17]            # ties: earliest win


def test_demo_prune_removes_only_old_visitor_responses(tmp_path):
    s = make_store(tmp_path)
    room = s.ensure_demo("Demo", "Lagos", "party", [("Seed", [{"text": "a", "kind": "any"}])])
    s.add_response(room, "Visitor", [{"text": "b", "kind": "any"}])
    assert s.prune_demo() == 0                                             # fresh visitor responses stay
    from datetime import timedelta
    assert s.prune_demo(older_than=timedelta(seconds=-5)) == 1             # old ones go, the seed stays
    assert [r.member_name for r in s.responses(room.id)] == ["Seed"]
    s.ensure_demo("Demo", "Lagos", "party", [("Seed", [{"text": "a", "kind": "any"}])])  # idempotent
    assert len(s.responses(room.id)) == 1


# ---- API ---------------------------------------------------------------------------------------

@pytest.fixture
def api(offline_client, monkeypatch):
    monkeypatch.setattr(main, "qloo", offline_client)
    monkeypatch.setattr(main, "llm", FakeLLM())
    for name, rate in (("_rooms_item", "100/hour"), ("_join_item", "100/hour"), ("_read_item", "1000/minute"), ("_item", "100/hour")):
        monkeypatch.setattr(ratelimit, name, parse(rate))
    ratelimit.reset()
    return TestClient(main.app, raise_server_exceptions=False)


def new_room(api, **kw):
    body = {"community_name": "Lagos Crew", "city": "Lagos", "event_goal": "launch party", **kw}
    r = api.post("/api/rooms", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def join(api, slug, name, *tastes):
    return api.post(f"/api/rooms/{slug}/join", json={"member_name": name, "tastes": [t if isinstance(t, dict) else {"text": t, "kind": "any"} for t in tastes]})


def org(token):
    return {"X-Organizer-Token": token}


def test_create_room_returns_token_once_and_links(api):
    r = new_room(api)
    assert len(r["slug"]) == 8 and len(r["organizer_token"]) >= 30
    assert r["join_path"] == f"/join/{r['slug']}" and r["organizer_path"] == f"/room/{r['slug']}?t={r['organizer_token']}"
    info = api.get(f"/api/rooms/{r['slug']}").json()
    assert info == {"slug": r["slug"], "community_name": "Lagos Crew", "city": "Lagos", "event_goal": "launch party",
                    "response_count": 0, "demo": False}
    assert "organizer_token" not in str(info)                              # the public view never carries it


def test_create_room_validates_and_is_rate_limited(api, monkeypatch):
    assert api.post("/api/rooms", json={"community_name": "", "city": "x", "event_goal": "y"}).status_code == 422
    assert api.post("/api/rooms", json={"community_name": "x" * 81, "city": "x", "event_goal": "y"}).status_code == 422
    monkeypatch.setattr(ratelimit, "_rooms_item", parse("2/hour"))
    ratelimit.reset()
    assert [api.post("/api/rooms", json={"community_name": "a", "city": "b", "event_goal": "c"}).status_code for _ in range(3)] == [200, 200, 429]
    assert "rooms" in api.post("/api/rooms", json={"community_name": "a", "city": "b", "event_goal": "c"}).json()["error"]


def test_unknown_room_is_a_friendly_404(api):
    r = api.get("/api/rooms/nosuchroom")
    assert r.status_code == 404 and "not found" in r.json()["error"]
    assert join(api, "nosuchroom", "Ada", "x").status_code == 404


def test_join_stores_cleaned_data_and_the_public_count_grows(api):
    slug = new_room(api)["slug"]
    r = join(api, slug, "  Ada  ", {"text": " Burna   Boy ", "kind": "artist"}, "Nike")
    assert r.status_code == 200 and r.json() == {"ok": True, "count": 1}
    assert api.get(f"/api/rooms/{slug}").json()["response_count"] == 1


def test_join_rejects_bad_input_with_friendly_messages(api):
    slug = new_room(api)["slug"]
    cases = [("ada@mail.com", ["x"], "first name or nickname"), ("", ["x"], None), ("Ada", [], None),
             ("Ada", [f"t{i}" for i in range(7)], None)]
    for name, tastes, text in cases:
        r = join(api, slug, name, *tastes)
        assert r.status_code == 422 and "error" in r.json() and "Traceback" not in r.text
        if text:
            assert text in r.json()["error"]
    assert join(api, slug, "Ada", "x").status_code == 200
    dup = join(api, slug, "ada", "y")
    assert dup.status_code == 409 and "already used that name" in dup.json()["error"]


def test_join_verifies_picked_entities_and_ignores_browser_supplied_names_and_images(offline_client, monkeypatch):
    c = Recorder(entities={UUID_A: raw("Burna Boy", UUID_A, image="https://images.qloo.com/real.jpg")})
    monkeypatch.setattr(main, "qloo", c)
    monkeypatch.setattr(ratelimit, "_join_item", parse("100/hour")); ratelimit.reset()
    api = TestClient(main.app, raise_server_exceptions=False)
    slug = api.post("/api/rooms", json={"community_name": "a", "city": "b", "event_goal": "c"}).json()["slug"]
    body = {"member_name": "Ada", "tastes": [
        {"text": "burna", "kind": "artist", "entity_id": UUID_A.lower(), "name": "<script>x</script>", "image": "javascript:alert(1)"},
        {"text": "Ghost", "kind": "artist", "entity_id": UUID_B}]}                    # an id Qloo does not know
    assert api.post(f"/api/rooms/{slug}/join", json=body).status_code == 200
    stored = rooms.get_store().responses(rooms.get_store().get_room(slug).id)[0].tastes
    assert stored[0]["name"] == "Burna Boy" and stored[0]["image"] == "https://images.qloo.com/real.jpg" and stored[0]["entity_id"] == UUID_A
    assert "script" not in str(stored) and "javascript" not in str(stored)
    assert "entity_id" not in stored[1]                                                # unknown id dropped: matched by text later
    assert [p for p, _ in c.calls] == ["/entities"]                                    # one batched check


def test_organizer_endpoints_need_the_token_in_a_header(api):
    r = new_room(api)
    slug, token = r["slug"], r["organizer_token"]
    join(api, slug, "Ada", "Burna Boy")
    ok = api.get(f"/api/rooms/{slug}/responses", headers=org(token))
    assert ok.status_code == 200 and ok.json()["responses"][0]["name"] == "Ada"
    msgs = set()
    for headers, path in [({}, f"/api/rooms/{slug}/responses"), (org("wrong"), f"/api/rooms/{slug}/responses"),
                          (org(token), "/api/rooms/nosuchroom/responses"), ({}, f"/api/rooms/{slug}/responses?t={token}")]:
        x = api.get(path, headers=headers)
        assert x.status_code == 404 and "tastes" not in x.text and "Ada" not in x.text
        msgs.add(x.json()["error"])
    assert len(msgs) == 1                                                                # no oracle for "room exists" vs "bad token"
    assert api.post(f"/api/rooms/{slug}/plan").status_code == 404
    assert api.delete(f"/api/rooms/{slug}/responses/1").status_code == 404


def test_organizer_can_remove_a_response(api):
    r = new_room(api); slug, token = r["slug"], r["organizer_token"]
    join(api, slug, "Spammer", "junk")
    rid = api.get(f"/api/rooms/{slug}/responses", headers=org(token)).json()["responses"][0]["id"]
    assert api.delete(f"/api/rooms/{slug}/responses/{rid}", headers=org("nope")).status_code == 404
    assert api.delete(f"/api/rooms/{slug}/responses/{rid}", headers=org(token)).json() == {"ok": True}
    assert api.get(f"/api/rooms/{slug}/responses", headers=org(token)).json()["responses"] == []
    assert api.delete(f"/api/rooms/{slug}/responses/{rid}", headers=org(token)).status_code == 404


def test_join_is_rate_limited_per_ip(api, monkeypatch):
    slug = new_room(api)["slug"]
    monkeypatch.setattr(ratelimit, "_join_item", parse("2/hour")); ratelimit.reset()
    assert [join(api, slug, n, "x").status_code for n in ("A", "B", "C")] == [200, 200, 429]


def fill(api, slug, n, tastes=("Burna Boy", "Nike")):
    for i in range(n):
        assert join(api, slug, f"Member{i}", *tastes).status_code == 200


def test_plan_needs_three_responses_then_builds_a_normal_plan(api):
    r = new_room(api); slug, token = r["slug"], r["organizer_token"]
    fill(api, slug, 2)
    few = api.post(f"/api/rooms/{slug}/plan", headers=org(token))
    assert few.status_code == 422 and "at least 3" in few.json()["error"] and "2 so far" in few.json()["error"]
    fill_more = join(api, slug, "Member9", "Burna Boy", "Nike"); assert fill_more.status_code == 200
    plan = api.post(f"/api/rooms/{slug}/plan", headers=org(token))
    assert plan.status_code == 200
    p = plan.json()
    assert p["mode"] == "agent" and p["request"]["community_name"] == "Lagos Crew" and p["request"]["city"] == "Lagos"
    assert [m["name"] for m in p["request"]["members"]] == ["Member0", "Member1", "Member9"]
    assert p["recommendations"]["music"] and p["brief"]["title"]
    assert api.get(f"/api/plan/{p['plan_id']}").json()["plan_id"] == p["plan_id"]       # saved like any plan
    again = api.post(f"/api/rooms/{slug}/plan", headers=org(token)).json()
    assert again["plan_id"] == p["plan_id"]                                              # cached: building again is free


def test_plan_from_a_big_room_uses_the_15_best_matched_and_says_so(api, monkeypatch):
    r = new_room(api); slug, token = r["slug"], r["organizer_token"]
    store = rooms.get_store(); room = store.get_room(slug)
    for i in range(18):   # members 0-2 typed text only (0 matched); the rest have a verified Qloo id
        tastes = [{"text": "Burna Boy", "kind": "artist"}] if i < 3 else [{"text": "Burna Boy", "kind": "artist", "entity_id": UUID_A}]
        store.add_response(room, f"M{i:02d}", tastes)
    info = api.get(f"/api/rooms/{slug}/responses", headers=org(token)).json()
    assert info["plan"] == {"will_use": 15, "left_out": ["M00", "M01", "M02"], "cap": 15, "min": 3}
    p = api.post(f"/api/rooms/{slug}/plan", headers=org(token)).json()
    assert len(p["request"]["members"]) == 15 and "M00" not in str(p["request"]["members"])
    assert any("18 members responded" in w and "M00, M01, M02" in w for w in p["warnings"])
    assert all(t["entity_id"] == UUID_A for m in p["request"]["members"] for t in m["tastes"])   # picks travel as ids


def test_plan_from_room_shares_the_plan_quota(api, monkeypatch):
    r = new_room(api); slug, token = r["slug"], r["organizer_token"]; fill(api, slug, 3)
    monkeypatch.setattr(ratelimit, "_item", parse("1/hour")); ratelimit.reset()
    assert api.post(f"/api/rooms/{slug}/plan", headers=org(token)).status_code == 200
    join(api, slug, "Extra", "Burna Boy", "Nike")                                         # new request: not cached
    limited = api.post(f"/api/rooms/{slug}/plan", headers=org(token))
    assert limited.status_code == 429 and "limited" in limited.json()["error"]


def test_storage_failure_makes_rooms_unavailable_without_breaking_the_app(api, monkeypatch):
    rooms.set_store(None)
    monkeypatch.setattr(rooms, "RoomStore", lambda path: (_ for _ in ()).throw(PermissionError("read-only")))
    r = api.post("/api/rooms", json={"community_name": "a", "city": "b", "event_goal": "c"})
    assert r.status_code == 503 and "temporarily unavailable" in r.json()["error"]
    assert api.get("/api/health").json()["ok"] is True and api.get("/api/examples").status_code == 200


# ---- demo room ---------------------------------------------------------------------------------

def test_demo_room_is_seeded_and_its_plan_is_instant_until_someone_joins(api, monkeypatch):
    seed_demo(); seed_demo()                                                              # idempotent
    info = api.get(f"/api/rooms/{DEMO_SLUG}").json()
    assert info["demo"] is True and info["response_count"] == 8 and info["community_name"] == "Lagos Creators"
    assert api.get(f"/api/rooms/{DEMO_SLUG}/responses", headers=org("nope")).status_code == 404
    got = api.get(f"/api/rooms/{DEMO_SLUG}/responses", headers=org(DEMO_TOKEN)).json()
    assert [r["name"] for r in got["responses"]][:3] == ["Ada", "Tunde", "Chioma"]

    async def boom(*a, **k):
        raise AssertionError("make_plan must not run: the demo plan is pre-cached")
    monkeypatch.setattr(planner, "make_plan", boom)
    plan = api.post(f"/api/rooms/{DEMO_SLUG}/plan", headers=org(DEMO_TOKEN))
    assert plan.status_code == 200 and plan.json()["mode"] == "precomputed" and len(plan.json()["request"]["members"]) == 8
    assert plan.json()["recommendations"]["music"]
    # a judge adds themselves: the request changes, so it is no longer the saved plan
    assert join(api, DEMO_SLUG, "Judge", "Burna Boy", "Nike").status_code == 200
    with pytest.raises(AssertionError):
        TestClient(main.app).post(f"/api/rooms/{DEMO_SLUG}/plan", headers=org(DEMO_TOKEN))


def test_demo_room_is_capped_small(api, monkeypatch):
    seed_demo()
    for i in range(7):
        assert join(api, DEMO_SLUG, f"V{i}", "x").status_code == 200
    full = join(api, DEMO_SLUG, "V8", "x")
    assert full.status_code == 409 and "demo room is full" in full.json()["error"]
