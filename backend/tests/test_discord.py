"""Post an announcement to Discord: the webhook URL is a credential, so it is validated hard, used once and never kept."""
import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from limits import parse

from app import discord, main, ratelimit
from app.errors import ApiError
from app.models import PlanResponse
from tests.fakes import FakeLLM

PRECOMPUTED = Path(__file__).resolve().parents[1] / "precomputed"
TOKEN = "T0kenAbCdEfGhIjKlMnOpQrStUvWxYz-_0123456789abcdefghij"
ID = "1234567890123456789"
URL = f"https://discord.com/api/webhooks/{ID}/{TOKEN}"


def example(eid="lagos-creators") -> PlanResponse:
    return PlanResponse.model_validate(json.loads((PRECOMPUTED / f"{eid}.json").read_text())["plan"])


@pytest.mark.parametrize("url", [
    URL, f"  {URL}  ", URL + "/", f"https://discordapp.com/api/webhooks/{ID}/{TOKEN}", f"https://canary.discord.com/api/v10/webhooks/{ID}/{TOKEN}",
])
def test_real_discord_webhook_urls_are_accepted(url):
    assert discord.parse_webhook(url) == (ID, TOKEN)


@pytest.mark.parametrize("url", [
    "", "not a url", f"http://discord.com/api/webhooks/{ID}/{TOKEN}",                    # not https
    f"https://evil.example/api/webhooks/{ID}/{TOKEN}",                                   # other host
    f"https://discord.com.evil.example/api/webhooks/{ID}/{TOKEN}",                       # look-alike host
    f"https://discord.com@evil.example/api/webhooks/{ID}/{TOKEN}",                       # userinfo trick
    f"https://evil.example/https://discord.com/api/webhooks/{ID}/{TOKEN}",
    f"https://discord.com:444/api/webhooks/{ID}/{TOKEN}", f"https://discord.com/api/webhooks/{ID}/{TOKEN}?thread_id=1",
    f"https://discord.com/api/webhooks/{ID}/{TOKEN}/../../x", f"https://discord.com/api/webhooks/12/{TOKEN}",
    f"https://discord.com/api/webhooks/{ID}/short", f"https://127.0.0.1/api/webhooks/{ID}/{TOKEN}",
    f"https://discord.com/api/webhooks/{ID}/{TOKEN}\nhttps://evil.example",
])
def test_anything_else_is_rejected_without_repeating_it(url):
    with pytest.raises(ApiError) as e:
        discord.parse_webhook(url)
    assert e.value.status == 422 and TOKEN not in e.value.message and "evil" not in e.value.message


def test_the_message_has_the_promo_line_the_top_venue_and_three_artists():
    plan = example()
    p = discord.announcement(plan, "https://x.test/plan/abc?shared=1")
    b = plan.brief
    assert p["content"] == b.promo_line
    e = p["embeds"][0]
    assert e["title"] == b.title and e["url"] == "https://x.test/plan/abc?shared=1"
    venue, artists = e["fields"]
    assert venue["name"] == "Venue" and venue["value"].startswith(b.venue[0].name)
    assert artists["name"] == "Artists" and artists["value"].splitlines() == [f"• {m.name}" for m in b.music[:3]]


def test_the_message_cannot_ping_anyone_and_respects_discords_length_limits():
    plan = example()
    plan = plan.model_copy(update={"brief": plan.brief.model_copy(update={"promo_line": "@everyone " + "x" * 5000, "title": "T" * 999, "concept": "c" * 999})})
    p = discord.announcement(plan, None)
    assert p["allowed_mentions"] == {"parse": []}
    assert len(p["content"]) <= 2000 and len(p["embeds"][0]["title"]) <= 256 and len(p["embeds"][0]["description"]) <= 400
    assert "url" not in p["embeds"][0]
    assert all(len(f["value"]) <= 1024 for f in p["embeds"][0]["fields"])


# ---- the route ------------------------------------------------------------------------------------------------------

class Fake:
    """Stands in for Discord. Records every request it receives."""

    def __init__(self, status=204, raises=False):
        self.requests, self.status, self.raises = [], status, raises

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raises:
            raise httpx.ConnectError(f"boom while connecting to {request.url}")
        return httpx.Response(self.status, headers={"location": "https://evil.example/"} if self.status == 302 else {})


@pytest.fixture
def api(monkeypatch):
    fake = Fake()
    monkeypatch.setattr(discord, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: fake.handler(r)), follow_redirects=False))
    monkeypatch.setattr(main, "llm", FakeLLM())
    for name, rate in (("_item", "100/hour"), ("_read_item", "1000/minute"), ("_discord_item", "100/hour")):
        monkeypatch.setattr(ratelimit, name, parse(rate))
    ratelimit.reset()
    c = TestClient(main.app, raise_server_exceptions=False)
    c.fake = fake  # type: ignore[attr-defined]
    return c


def test_preview_is_exactly_what_gets_posted(api):
    preview = api.get("/api/plan/lagos-creators/announcement", headers={"host": "tasteroom.test"}).json()["payload"]
    assert api.post("/api/plan/lagos-creators/discord", json={"webhook_url": URL}, headers={"host": "tasteroom.test"}).json() == {"ok": True}
    (req,) = api.fake.requests
    assert json.loads(req.content) == preview
    assert preview["embeds"][0]["url"] == "http://tasteroom.test/example/lagos-creators"


def test_a_built_plan_links_to_its_read_only_view_with_the_forwarded_scheme(api):
    plan = example()
    child = plan.model_copy(update={"plan_id": "abc123def456"})
    from app import planner
    planner.store_plan(child)
    url = api.get("/api/plan/abc123def456/announcement", headers={"host": "tasteroom.test", "x-forwarded-proto": "https"}).json()["payload"]["embeds"][0]["url"]
    assert url == "https://tasteroom.test/plan/abc123def456?shared=1"


def test_we_post_to_discord_com_at_an_address_we_built_and_never_follow_redirects(api):
    api.post("/api/plan/lagos-creators/discord", json={"webhook_url": f"https://canary.discordapp.com/api/v9/webhooks/{ID}/{TOKEN}/"})
    (req,) = api.fake.requests
    assert str(req.url) == URL and req.method == "POST"
    api.fake.status = 302
    r = api.post("/api/plan/lagos-creators/discord", json={"webhook_url": URL})
    assert r.status_code == 502 and len(api.fake.requests) == 2           # the redirect was not followed


def test_a_bad_url_is_rejected_before_anything_is_sent_or_any_quota_is_used(api, monkeypatch):
    monkeypatch.setattr(ratelimit, "_discord_item", parse("1/hour")); ratelimit.reset()
    for bad in ("https://evil.example/hook", f"http://discord.com/api/webhooks/{ID}/{TOKEN}", ""):
        r = api.post("/api/plan/lagos-creators/discord", json={"webhook_url": bad})
        assert r.status_code == 422 and "Discord webhook" in r.json()["error"]
    assert api.fake.requests == []
    assert api.post("/api/plan/lagos-creators/discord", json={"webhook_url": URL}).status_code == 200   # the single allowed post is still free
    assert api.post("/api/plan/lagos-creators/discord", json={"webhook_url": URL}).status_code == 429


def test_unknown_plan_and_oversized_url(api):
    assert api.post("/api/plan/doesnotexist/discord", json={"webhook_url": URL}).status_code == 404
    assert api.post("/api/plan/lagos-creators/discord", json={"webhook_url": URL + "a" * 400}).status_code == 422
    assert api.fake.requests == []


@pytest.mark.parametrize("status,expect", [(404, 422), (401, 422), (400, 422), (429, 429), (500, 502)])
def test_discord_errors_become_friendly_messages(api, status, expect):
    api.fake.status = status
    r = api.post("/api/plan/lagos-creators/discord", json={"webhook_url": URL})
    assert r.status_code == expect and TOKEN not in r.text and "error" in r.json()


def test_the_token_never_appears_in_logs_responses_or_files(api, caplog, tmp_path):
    caplog.set_level(logging.DEBUG)
    bodies = [api.post("/api/plan/lagos-creators/discord", json={"webhook_url": URL}).text]
    api.fake.raises = True
    bodies.append(api.post("/api/plan/lagos-creators/discord", json={"webhook_url": URL}).text)   # the transport error text contains the URL
    api.fake.raises, api.fake.status = False, 500
    bodies.append(api.post("/api/plan/lagos-creators/discord", json={"webhook_url": URL}).text)
    bodies.append(api.post("/api/plan/lagos-creators/discord", json={"webhook_url": 5}).text)     # a validation error must not echo the input
    assert bodies[1] and json.loads(bodies[1])["error"].startswith("Could not reach Discord")
    assert TOKEN not in "\n".join(bodies)
    assert TOKEN not in caplog.text and TOKEN not in "\n".join(str(r.__dict__) for r in caplog.records)
    for f in tmp_path.rglob("*"):                                                                   # the cache and the SQLite database
        if f.is_file():
            assert TOKEN.encode() not in f.read_bytes(), f"webhook token found stored in {f.name}"
