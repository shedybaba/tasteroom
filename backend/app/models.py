"""Pydantic models (BUILD_PLAN.md section 6). Mirrored in frontend/src/types.ts."""
from typing import Literal

from pydantic import BaseModel


class Taste(BaseModel):
    text: str
    kind: Literal[
        "artist", "tv_show", "movie", "brand", "place", "podcast", "book", "video_game", "any"
    ] = "any"


class Member(BaseModel):
    name: str
    tastes: list[Taste]


class PlanOptions(BaseModel):
    hidden_gems: bool = False
    price_level_max: int | None = None
    day: str | None = None
    venue_kind: str | None = None


class PlanRequest(BaseModel):
    community_name: str
    city: str
    event_goal: str
    members: list[Member]
    options: PlanOptions = PlanOptions()


class SlimEntity(BaseModel):
    id: str
    name: str
    type: str
    popularity: float | None = None
    description: str | None = None
    image: str | None = None
    address: str | None = None
    website: str | None = None
    tags: list[str] = []
    tag_ids: list[str] = []
    # Filled only for insights results. `affinity` is Qloo's own score for the result;
    # `explain` maps each input entity id -> its share of the score (native explainability).
    affinity: float | None = None
    explain: dict[str, float] = {}


class ResolvedTaste(BaseModel):
    member: str
    input: str
    entity: SlimEntity | None


class Contribution(BaseModel):
    member: str
    score: float
    via: list[str]


class Recommendation(BaseModel):
    entity: SlimEntity
    domain: Literal["music", "venues", "brands", "content"]
    why: list[Contribution]
    shared_tags: list[str] = []
    explanation_method: Literal["qloo_explainability", "per_member_affinity", "tag_overlap"]


class TraceStep(BaseModel):
    step: int
    tool: str
    args: dict
    summary: str
    ms: int
    ok: bool


class BriefPick(BaseModel):
    entity_id: str
    name: str
    reason: str


class Brief(BaseModel):
    title: str
    concept: str
    vibe_words: list[str]
    run_of_show: list[str]
    music: list[BriefPick]
    venue: list[BriefPick]
    sponsors: list[BriefPick]
    content: list[BriefPick]
    promo_line: str


class PlanResponse(BaseModel):
    plan_id: str
    request: PlanRequest
    resolved: list[ResolvedTaste]
    locality: SlimEntity | None
    recommendations: dict[str, list[Recommendation]]
    brief: Brief
    trace: list[TraceStep]
    mode: Literal["agent", "pipeline", "precomputed", "mock"]
    warnings: list[str] = []


class ResolveRequest(BaseModel):
    members: list[Member]
    city: str


class ResolveResponse(BaseModel):
    resolved: list[ResolvedTaste]
    locality: SlimEntity | None
