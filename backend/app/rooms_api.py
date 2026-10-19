"""HTTP routes for invite rooms (see rooms.py for storage and safety notes)."""
import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from . import planner, ratelimit, rooms
from .config import REPO_ROOT
from .errors import ApiError
from .examples import EXAMPLES
from .models import Member, PlanRequest, PlanResponse, Taste
from .qloo_client import QlooError
from .rooms import (DEMO_SLUG, MIN_RESPONSES_TO_PLAN, PLAN_MEMBER_CAP, Room, RoomError, StoredResponse,
                    clean_member_name, clean_tastes, clean_text, select_for_plan)

log = logging.getLogger("tasteroom.rooms")
router = APIRouter(prefix="/api/rooms")

NOT_FOUND = "That room or organizer link was not found."  # one message for "no such room" and "wrong token"


class CreateRoom(BaseModel):
    community_name: str = Field(min_length=1, max_length=80)
    city: str = Field(min_length=1, max_length=80)
    event_goal: str = Field(min_length=1, max_length=200)


class JoinRoom(BaseModel):
    member_name: str = Field(min_length=1, max_length=60)
    tastes: list[Taste] = Field(min_length=1, max_length=6)


def _main():
    from . import main  # late import: main imports this module, and tests patch main.qloo / main.llm
    return main


def _store() -> rooms.RoomStore:
    try:
        return rooms.get_store()
    except OSError as exc:  # unwritable DATA_DIR: rooms are down, the rest of the app is not
        log.error("room storage unavailable: %s", type(exc).__name__)
        raise ApiError(503, "Invite rooms are temporarily unavailable. Please try again shortly.") from exc


def _public(room: Room, store: rooms.RoomStore) -> dict[str, Any]:
    return {"slug": room.slug, "community_name": room.community_name, "city": room.city, "event_goal": room.event_goal,
            "response_count": store.count(room.id), "demo": room.slug == DEMO_SLUG}


async def _authorize(request: Request, slug: str, token: str | None) -> tuple[rooms.RoomStore, Room]:
    if not ratelimit.allow_room_read(request):
        raise ApiError(429, "Too many requests. Give it a few seconds.")
    store = _store()
    room = await asyncio.to_thread(store.get_room, slug)
    if room is None or not await asyncio.to_thread(store.check_token, slug, token or ""):
        raise ApiError(404, NOT_FOUND)
    return store, room


def _response_json(r: StoredResponse) -> dict[str, Any]:
    return {"id": r.id, "name": r.member_name, "created_at": r.created_at, "matched": r.matched, "tastes": r.tastes}


@router.post("")
async def create_room(body: CreateRoom, request: Request) -> dict[str, Any]:
    if not ratelimit.allow_rooms(request):
        raise ApiError(429, "You have created a lot of rooms in the last hour. Reuse one of them or try again later.")
    store = _store()
    room, token = await asyncio.to_thread(
        store.create_room, clean_text(body.community_name, 80), clean_text(body.city, 80), clean_text(body.event_goal, 200))
    # The token is returned this once; only its hash is stored.
    return {"slug": room.slug, "organizer_token": token, "join_path": f"/join/{room.slug}",
            "organizer_path": f"/room/{room.slug}?t={token}"}


@router.get("/{slug}")
async def room_info(slug: str, request: Request) -> dict[str, Any]:
    """What a member sees on the join page: the event, never anyone's answers."""
    if not ratelimit.allow_room_read(request):
        raise ApiError(429, "Too many requests. Give it a few seconds.")
    store = _store()
    room = await asyncio.to_thread(store.get_room, slug)
    if room is None:
        raise ApiError(404, "That room was not found. Check the link you were sent.")
    return await asyncio.to_thread(_public, room, store)


@router.post("/{slug}/join")
async def join_room(slug: str, body: JoinRoom, request: Request) -> dict[str, Any]:
    if not ratelimit.allow_join(request):
        raise ApiError(429, "That is a lot of submissions from one place. Try again in a little while.")
    store = _store()
    room = await asyncio.to_thread(store.get_room, slug)
    if room is None:
        raise ApiError(404, "That room was not found. Check the link you were sent.")
    name = clean_member_name(body.member_name)
    tastes = clean_tastes(body.tastes)
    tastes = await _verify_picks(tastes)
    await asyncio.to_thread(store.add_response, room, name, tastes)
    return {"ok": True, "count": await asyncio.to_thread(store.count, room.id)}


async def _verify_picks(tastes: list[dict]) -> list[dict]:
    """A picked suggestion carries a Qloo id. Check it is real and store Qloo's own name, image and type (never
    values sent by the browser). Unknown ids are dropped, so the taste is matched by its text later."""
    ids = sorted({t["entity_id"] for t in tastes if t.get("entity_id")})
    if not ids:
        return tastes
    try:
        found = {e.id: e for e in await _main().qloo.get_entities(ids)}
    except QlooError:
        return tastes  # Qloo hiccup: keep the ids; the plan falls back to a text search for any that turn out invalid
    out = []
    for t in tastes:
        e = found.get(t.get("entity_id", ""))
        if t.get("entity_id") and e is None:
            t = {k: v for k, v in t.items() if k != "entity_id"}
        elif e is not None:
            t = {**t, "name": e.name, "image": e.image, "type": e.type}
        out.append(t)
    return out


@router.get("/{slug}/responses")
async def room_responses(slug: str, request: Request, x_organizer_token: str | None = Header(default=None)) -> dict[str, Any]:
    store, room = await _authorize(request, slug, x_organizer_token)
    if room.slug == DEMO_SLUG:
        await asyncio.to_thread(store.prune_demo)
    responses = await asyncio.to_thread(store.responses, room.id)
    used, left = select_for_plan(responses)
    return {"room": _public(room, store) | {"response_count": len(responses)},
            "responses": [_response_json(r) for r in responses],
            "plan": {"will_use": len(used), "left_out": [r.member_name for r in left], "cap": PLAN_MEMBER_CAP,
                     "min": MIN_RESPONSES_TO_PLAN}}


@router.delete("/{slug}/responses/{response_id}")
async def remove_response(slug: str, response_id: int, request: Request,
                          x_organizer_token: str | None = Header(default=None)) -> dict[str, Any]:
    store, room = await _authorize(request, slug, x_organizer_token)
    removed = await asyncio.to_thread(store.delete_response, room.id, response_id)
    if not removed:
        raise ApiError(404, "That response was not found.")
    return {"ok": True}


def plan_request_for(room: Room, used: list[StoredResponse]) -> PlanRequest:
    return PlanRequest(
        community_name=room.community_name, city=room.city, event_goal=room.event_goal,
        members=[Member(name=r.member_name, tastes=[Taste(text=t["text"], kind=t["kind"], entity_id=t.get("entity_id"))
                                                    for t in r.tastes]) for r in used])


@router.post("/{slug}/plan", response_model=PlanResponse)
async def room_plan(slug: str, request: Request, x_organizer_token: str | None = Header(default=None)) -> PlanResponse:
    """Build a normal plan from the room's responses (the same pipeline, cache and quota as /api/plan)."""
    store, room = await _authorize(request, slug, x_organizer_token)
    responses = await asyncio.to_thread(store.responses, room.id)
    if len(responses) < MIN_RESPONSES_TO_PLAN:
        raise ApiError(422, f"You need at least {MIN_RESPONSES_TO_PLAN} responses to build a plan ({len(responses)} so far).")
    used, left = select_for_plan(responses)
    note = (f"{len(responses)} members responded. The plan uses the {len(used)} whose tastes Qloo matched best "
            f"(not included: {', '.join(r.member_name for r in left)}).") if left else None
    return await _main()._get_or_make_plan(plan_request_for(room, used), request, note=note)


# ---- demo room for judges ------------------------------------------------------------------------

def seed_demo() -> None:
    """Create the demo room (the Lagos Creators example) and pre-cache its plan, so a judge's "Build" is instant.
    Runs at startup; idempotent. Never raises: the demo is a convenience, not a dependency."""
    try:
        ex: PlanRequest = EXAMPLES["lagos-creators"]["request"]
        store = rooms.get_store()
        store.ensure_demo(ex.community_name, ex.city, ex.event_goal,
                          [(m.name, [{"text": t.text, "kind": t.kind} for t in m.tastes]) for m in ex.members])
        store.prune_demo()
        saved = REPO_ROOT / "backend" / "precomputed" / "lagos-creators.json"
        if saved.is_file():
            plan = PlanResponse.model_validate(json.loads(saved.read_text())["plan"])
            plan.plan_id, plan.mode = planner.plan_id_for(ex), "precomputed"  # same request hash as the room's 8 responses
            planner.store_plan(plan)
    except Exception as exc:  # noqa: BLE001
        log.warning("demo room seeding skipped: %s: %s", type(exc).__name__, str(exc)[:160])


__all__ = ["router", "seed_demo", "plan_request_for", "RoomError"]
