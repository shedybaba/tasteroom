"""Post a plan's announcement to a Discord channel through a webhook the organizer pastes in.

A webhook URL is a credential (the token in it is all it takes to post). So:
- it is never stored, cached or logged: it lives in the request, is used once and is dropped;
- we never POST to the URL the user typed. We pull the numeric id and the token out of it and POST to a discord.com
  URL we build ourselves, so this route cannot be pointed at any other host (no SSRF) and does not follow redirects;
- what gets posted is built here from the saved plan (the same function builds the preview the user confirms), so the
  route cannot be used to send arbitrary text through our server;
- the message cannot ping anyone (`allowed_mentions` is empty), even if a generated line contains @everyone."""
import logging
import re

import httpx

from .attribution import members_for
from .errors import ApiError
from .models import PlanResponse

# The httpx loggers print the full request URL at INFO level, which here would put the token in the logs.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

WEBHOOK = re.compile(r"https://(?:(?:canary|ptb)\.)?(?:discord|discordapp)\.com/api(?:/v\d+)?/webhooks/(\d{15,25})/([A-Za-z0-9_-]{20,120})/?")
COLOR = 0xE8472B  # the accent colour of the app


def parse_webhook(url: str) -> tuple[str, str]:
    """(webhook id, token) from a Discord webhook URL, or a friendly error that never repeats what was typed."""
    m = WEBHOOK.fullmatch((url or "").strip())
    if not m:
        raise ApiError(422, "That doesn't look like a Discord webhook URL. In Discord: channel settings > Integrations > Webhooks > "
                            "Copy Webhook URL. It starts with https://discord.com/api/webhooks/.")
    return m.group(1), m.group(2)


def _clip(text: str, n: int) -> str:
    text = "\n".join(" ".join(line.split()) for line in (text or "").strip().splitlines())  # tidy spaces, keep line breaks
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _personal_note(plan: PlanResponse, entity_id: str) -> str:
    """" (personal pick for Priya)" when the pick was chosen for a member, so the post says so too."""
    mine = members_for(plan.personal, "music", entity_id)
    return f" (personal pick for {' and '.join(p.member for p in mine)})" if mine else ""


def announcement(plan: PlanResponse, link: str | None) -> dict:
    """The exact Discord message for this plan: the promo line, the top venue and the first three artists."""
    b = plan.brief
    fields = []
    if b.venue:
        venue = next((r.entity for r in plan.recommendations.get("venues", []) if r.entity.id == b.venue[0].entity_id), None)
        where = " · ".join(x for x in (venue.neighborhood if venue else None, venue.address if venue else None) if x)
        fields.append({"name": "Venue", "value": _clip(b.venue[0].name + (f"\n{where}" if where else ""), 1024), "inline": False})
    if b.music:
        fields.append({"name": "Artists", "value": _clip("\n".join(f"• {p.name}{_personal_note(plan, p.entity_id)}" for p in b.music[:3]), 1024), "inline": False})
    embed = {"title": _clip(b.title, 256), "description": _clip(b.concept, 400), "color": COLOR, "fields": fields,
             "footer": {"text": "Picked from Qloo taste data · made with TasteRoom"}}
    if link:
        embed["url"] = link
    return {"username": "TasteRoom", "content": _clip(b.promo_line, 2000), "embeds": [embed], "allowed_mentions": {"parse": []}}


def _client() -> httpx.AsyncClient:  # a function so tests can swap in a fake transport
    return httpx.AsyncClient(timeout=10, follow_redirects=False)


async def post(webhook_url: str, payload: dict) -> None:
    wid, token = parse_webhook(webhook_url)
    try:
        async with _client() as client:
            resp = await client.post(f"https://discord.com/api/webhooks/{wid}/{token}", json=payload)
    except httpx.HTTPError:
        # `from None`: the original error text can contain the URL, so it must not be chained into logs or responses
        raise ApiError(502, "Could not reach Discord. Try again in a moment.") from None
    if resp.status_code in (200, 204):
        return
    if resp.status_code in (401, 404):
        raise ApiError(422, "Discord says that webhook doesn't exist any more. Create a new one in the channel's settings and paste it here.")
    if resp.status_code == 429:
        raise ApiError(429, "Discord is rate limiting that webhook. Wait a minute and try again.")
    if resp.status_code == 400:
        raise ApiError(422, "Discord rejected the message.")
    raise ApiError(502, f"Discord did not accept the post (status {resp.status_code}).")
