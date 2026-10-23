"""Post a plan's announcement to a Slack channel through an incoming-webhook URL the host pastes in.

Same rules as discord.py, because a Slack webhook URL is a credential too (anyone holding it can post to that channel):
- it is never stored, cached or logged: it lives in the request, is used once and is dropped;
- we never POST to the URL the user typed. We pull the three parts out of it and POST to a hooks.slack.com URL we build
  ourselves, so this route cannot be pointed at any other host (no SSRF) and does not follow redirects;
- what gets posted is built here from the saved plan (the same function builds the preview the user confirms), so the
  route cannot be used to send arbitrary text through our server;
- every piece of plan text is escaped (& < >), so a generated line can never become <!channel>, <@user> or a link."""
import logging
import re

import httpx

from .discord import _clip, venue_and_artists
from .errors import ApiError
from .models import PlanResponse

# The httpx loggers print the full request URL at INFO level, which here would put the token in the logs.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

WEBHOOK = re.compile(r"https://hooks\.slack\.com/services/(T[A-Z0-9]{7,12})/(B[A-Z0-9]{7,12})/([A-Za-z0-9]{20,40})/?")


def parse_webhook(url: str) -> tuple[str, str, str]:
    """(team id, bot id, token) from a Slack webhook URL, or a friendly error that never repeats what was typed."""
    m = WEBHOOK.fullmatch((url or "").strip())
    if not m:
        raise ApiError(422, "That doesn't look like a Slack webhook URL. In Slack: create an Incoming Webhook for the channel "
                            "(api.slack.com/messaging/webhooks) and copy its URL. It starts with https://hooks.slack.com/services/.")
    return m.group(1), m.group(2), m.group(3)


def _esc(text: str) -> str:
    """Slack's own rule: only & < > are special. Escaping them turns <!channel>, <@U123> and <http://x|y> into plain text."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mrkdwn(text: str, n: int) -> dict:
    return {"type": "mrkdwn", "text": _esc(_clip(text, n))}


def announcement(plan: PlanResponse, link: str | None) -> dict:
    """The exact Slack message for this plan: title, promo line, concept, the top venue and the first three artists."""
    b = plan.brief
    venue, artists = venue_and_artists(plan)
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": _clip(b.title, 150), "emoji": False}},
        {"type": "section", "text": _mrkdwn(b.promo_line, 3000)},
        {"type": "section", "text": _mrkdwn(b.concept, 400)},
    ]
    fields = []
    if venue:
        fields.append({"type": "mrkdwn", "text": "*Venue*\n" + _esc(_clip(venue, 1900))})
    if artists:
        fields.append({"type": "mrkdwn", "text": "*Artists*\n" + _esc(_clip(artists, 1900))})
    if fields:
        blocks.append({"type": "section", "fields": fields})
    if link:   # the link is ours (built from the request host and the plan id), so only & needs escaping
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"<{link.replace('&', '&amp;')}|See the full plan>"}})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Picked from Qloo taste data · made with TasteRoom"}]})
    # `text` is what notifications show; with blocks present Slack draws the blocks. Links are not expanded into previews.
    return {"text": _esc(_clip(b.promo_line, 3000)), "blocks": blocks, "unfurl_links": False, "unfurl_media": False}


def _client() -> httpx.AsyncClient:  # a function so tests can swap in a fake transport
    return httpx.AsyncClient(timeout=10, follow_redirects=False)


async def post(webhook_url: str, payload: dict) -> None:
    team, bot, token = parse_webhook(webhook_url)
    try:
        async with _client() as client:
            resp = await client.post(f"https://hooks.slack.com/services/{team}/{bot}/{token}", json=payload)
    except httpx.HTTPError:
        # `from None`: the original error text can contain the URL, so it must not be chained into logs or responses
        raise ApiError(502, "Could not reach Slack. Try again in a moment.") from None
    if resp.status_code == 200:
        return
    if resp.status_code in (403, 404):
        raise ApiError(422, "Slack says that webhook isn't valid any more (it may have been revoked or its app removed). "
                            "Create a new Incoming Webhook and paste it here.")
    if resp.status_code == 410:
        raise ApiError(422, "That Slack channel has been archived. Choose a webhook for an active channel.")
    if resp.status_code == 429:
        raise ApiError(429, "Slack is rate limiting that webhook. Wait a minute and try again.")
    if resp.status_code == 400:
        raise ApiError(422, "Slack rejected the message.")
    raise ApiError(502, f"Slack did not accept the post (status {resp.status_code}).")
