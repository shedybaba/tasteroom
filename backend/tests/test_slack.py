"""Post an announcement to Slack: the webhook URL is a credential, so it is validated hard, used once and never kept."""
import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from limits import parse

from app import discord, main, ratelimit, slack
from app.errors import ApiError
from app.models import PlanResponse
from tests.fakes import FakeLLM

PRECOMPUTED = Path(__file__).resolve().parents[1] / "precomputed"
TOKEN = "AbCdEfGhIjKlMnOpQrStUvWx"
TEAM, BOT = "T01234ABCDE", "B01234ABCDE"
URL = f"https://hooks.slack.com/services/{TEAM}/{BOT}/{TOKEN}"


def example(eid="lagos-creators") -> PlanResponse:
    return PlanResponse.model_validate(json.loads((PRECOMPUTED / f"{eid}.json").read_text())["plan"])


@pytest.mark.parametrize("url", [URL, f"  {URL}  ", URL + "/"])
def test_real_slack_webhook_urls_are_accepted(url):
    assert slack.parse_webhook(url) == (TEAM, BOT, TOKEN)


@pytest.mark.parametrize("url", [
    "", "not a url", f"http://hooks.slack.com/services/{TEAM}/{BOT}/{TOKEN}",             # not https
    f"https://evil.example/services/{TEAM}/{BOT}/{TOKEN}",                                # other host
    f"https://hooks.slack.com.evil.example/services/{TEAM}/{BOT}/{TOKEN}",                # look-alike host
    f"https://hooks.slack.com@evil.example/services/{TEAM}/{BOT}/{TOKEN}",                # userinfo trick
    f"https://evil.example/https://hooks.slack.com/services/{TEAM}/{BOT}/{TOKEN}",
    f"https://hooks.slack.com:444/services/{TEAM}/{BOT}/{TOKEN}", f"{URL}?x=1", f"{URL}/../../x",
    f"https://hooks.slack.com/services/{TEAM}/{BOT}/short", f"https://hooks.slack.com/services/X1/{BOT}/{TOKEN}",
    f"https://127.0.0.1/services/{TEAM}/{BOT}/{TOKEN}", f"{URL}\nhttps://evil.example",
    f"https://discord.com/api/webhooks/1234567890123456789/{TOKEN}{TOKEN}",              # a Discord URL is not a Slack URL
])
def test_anything_else_is_rejected_without_repeating_it(url):
    with pytest.raises(ApiError) as e:
        slack.parse_webhook(url)
    assert e.value.status == 422 and TOKEN not in e.value.message and "evil" not in e.value.message


def test_the_message_has_the_promo_line_the_top_venue_and_three_artists():
    plan = example()
    p = slack.announcement(plan, "https://x.test/plan/abc?shared=1")
    b = plan.brief
    assert p["text"] == b.promo_line
    header, promo, concept, fields, link, context = p["blocks"]
    assert header["text"]["text"] == b.title
    assert promo["text"]["text"] == b.promo_line
    venue, artists = fields["fields"]
    d_venue, d_artists = discord.venue_and_artists(plan)
    assert venue["text"] == f"*Venue*\n{d_venue}" and artists["text"] == f"*Artists*\n{d_artists}"   # same facts as the Discord post
    assert link["text"]["text"] == "<https://x.test/plan/abc?shared=1|See the full plan>"
    assert "made with TasteRoom" in context["elements"][0]["text"]


def test_plan_text_cannot_ping_anyone_or_make_a_link_and_respects_length_limits():
    plan = example()
    nasty = "<!channel> <@U123ABC> <https://evil.example|click> & more " + "x" * 5000
    plan = plan.model_copy(update={"brief": plan.brief.model_copy(update={"promo_line": nasty, "title": "T" * 999, "concept": nasty})})
    p = slack.announcement(plan, None)
    text = json.dumps(p)
    assert "<!channel>" not in text and "<@U123ABC>" not in text and "<https://evil.example" not in text   # all escaped
    assert "&lt;!channel&gt;" in p["blocks"][1]["text"]["text"] and "&amp; more" in p["blocks"][1]["text"]["text"]
    assert len(p["blocks"][0]["text"]["text"]) <= 150 and len(p["blocks"][1]["text"]["text"]) <= 3100 and len(p["blocks"][2]["text"]["text"]) <= 500
    assert all(len(f["text"]) <= 2000 for blk in p["blocks"] if blk["type"] == "section" and "fields" in blk for f in blk["fields"])
    assert not any("<http" in json.dumps(blk) for blk in p["blocks"])      # with no link given there is no link block


# ---- the route ------------------------------------------------------------------------------------------------------

class Fake:
    """Stands in for Slack. Records every request it receives."""

    def __init__(self, status=200, raises=False):
        self.requests, self.status, self.raises = [], status, raises

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raises:
            raise httpx.ConnectError(f"boom while connecting to {request.url}")
        return httpx.Response(self.status, text="ok", headers={"location": "https://evil.example/"} if self.status == 302 else {})


@pytest.fixture
def api(monkeypatch):
    fake = Fake()
    monkeypatch.setattr(slack, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: fake.handler(r)), follow_redirects=False))
    monkeypatch.setattr(main, "llm", FakeLLM())
    for name, rate in (("_item", "100/hour"), ("_read_item", "1000/minute"), ("_slack_item", "100/hour")):
        monkeypatch.setattr(ratelimit, name, parse(rate))
    ratelimit.reset()
    c = TestClient(main.app, raise_server_exceptions=False)
    c.fake = fake  # type: ignore[attr-defined]
    return c


def test_preview_is_exactly_what_gets_posted(api):
    preview = api.get("/api/plan/lagos-creators/announcement?service=slack", headers={"host": "tasteroom.test"}).json()["payload"]
    assert api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL}, headers={"host": "tasteroom.test"}).json() == {"ok": True}
    (req,) = api.fake.requests
    assert json.loads(req.content) == preview
    assert "http://tasteroom.test/example/lagos-creators|See the full plan" in json.dumps(preview)


def test_the_announcement_route_still_defaults_to_discord_and_rejects_other_services(api):
    assert "embeds" in api.get("/api/plan/lagos-creators/announcement").json()["payload"]
    assert "blocks" in api.get("/api/plan/lagos-creators/announcement?service=slack").json()["payload"]
    assert api.get("/api/plan/lagos-creators/announcement?service=teams").status_code == 422


def test_we_post_to_hooks_slack_com_at_an_address_we_built_and_never_follow_redirects(api):
    api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL + "/"})
    (req,) = api.fake.requests
    assert str(req.url) == URL and req.method == "POST"
    api.fake.status = 302
    r = api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL})
    assert r.status_code == 502 and len(api.fake.requests) == 2           # the redirect was not followed


def test_a_bad_url_is_rejected_before_anything_is_sent_or_any_quota_is_used(api, monkeypatch):
    monkeypatch.setattr(ratelimit, "_slack_item", parse("1/hour")); ratelimit.reset()
    for bad in ("https://evil.example/hook", f"http://hooks.slack.com/services/{TEAM}/{BOT}/{TOKEN}", ""):
        r = api.post("/api/plan/lagos-creators/slack", json={"webhook_url": bad})
        assert r.status_code == 422 and "Slack webhook" in r.json()["error"]
    assert api.fake.requests == []
    assert api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL}).status_code == 200   # the single allowed post is still free
    assert api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL}).status_code == 429


def test_slack_and_discord_have_separate_limits(api, monkeypatch):
    monkeypatch.setattr(discord, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(204)), follow_redirects=False))
    monkeypatch.setattr(ratelimit, "_slack_item", parse("1/hour")); ratelimit.reset()
    assert api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL}).status_code == 200
    assert api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL}).status_code == 429
    assert api.post("/api/plan/lagos-creators/discord", json={"webhook_url": "https://discord.com/api/webhooks/1234567890123456789/" + "a" * 40}).status_code == 200


def test_unknown_plan_and_oversized_url(api):
    assert api.post("/api/plan/doesnotexist/slack", json={"webhook_url": URL}).status_code == 404
    assert api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL + "a" * 400}).status_code == 422
    assert api.fake.requests == []


@pytest.mark.parametrize("status,expect", [(404, 422), (403, 422), (410, 422), (400, 422), (429, 429), (500, 502)])
def test_slack_errors_become_friendly_messages(api, status, expect):
    api.fake.status = status
    r = api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL})
    assert r.status_code == expect and TOKEN not in r.text and "error" in r.json()


def test_the_token_never_appears_in_logs_responses_or_files(api, caplog, tmp_path):
    caplog.set_level(logging.DEBUG)
    bodies = [api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL}).text]
    api.fake.raises = True
    bodies.append(api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL}).text)   # the transport error text contains the URL
    api.fake.raises, api.fake.status = False, 500
    bodies.append(api.post("/api/plan/lagos-creators/slack", json={"webhook_url": URL}).text)
    bodies.append(api.post("/api/plan/lagos-creators/slack", json={"webhook_url": 5}).text)     # a validation error must not echo the input
    assert bodies[1] and json.loads(bodies[1])["error"].startswith("Could not reach Slack")
    assert TOKEN not in "\n".join(bodies)
    assert TOKEN not in caplog.text and TOKEN not in "\n".join(str(r.__dict__) for r in caplog.records)
    for f in tmp_path.rglob("*"):                                                                   # the cache and the SQLite database
        if f.is_file():
            assert TOKEN.encode() not in f.read_bytes(), f"webhook token found stored in {f.name}"
