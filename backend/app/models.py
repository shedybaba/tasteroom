"""Pydantic models (BUILD_PLAN.md section 6). Mirrored in frontend/src/types.ts."""
from typing import Literal

from pydantic import BaseModel, Field


class Taste(BaseModel):
    text: str = Field(max_length=80)
    kind: Literal[
        "artist", "tv_show", "movie", "brand", "place", "podcast", "book", "video_game", "any"
    ] = "any"


class Member(BaseModel):
    name: str = Field(max_length=60)
    tastes: list[Taste] = Field(min_length=1, max_length=6)


class PlanOptions(BaseModel):
    hidden_gems: bool = False
    price_level_max: int | None = None
    day: str | None = None
    venue_kind: str | None = None


class PlanRequest(BaseModel):
    community_name: str = Field(min_length=1, max_length=80)
    city: str = Field(max_length=80)
    event_goal: str = Field(min_length=1, max_length=200)
    members: list[Member] = Field(min_length=3, max_length=15)
    options: PlanOptions = PlanOptions()


class SlimEntity(BaseModel):
    id: str
    name: str
    type: str
    popularity: float | None = None
    description: str | None = None
    image: str | None = None
    address: str | None = None
    city: str | None = None      # properties.geocode.city (places); used to verify "venue is in the city"
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
    dropped_picks: int = 0       # brief picks removed by the grounding validator


class ResolveRequest(BaseModel):
    members: list[Member] = Field(max_length=15)
    city: str = Field(max_length=80)


class ResolveResponse(BaseModel):
    resolved: list[ResolvedTaste]
    locality: SlimEntity | None


# ---- Compare tab (LLM-only baseline) ----

class BaselinePick(BaseModel):
    name: str
    reason: str


class BaselineBrief(BaseModel):
    """Same shape as Brief, but picks carry no Qloo entity ids: the LLM had no Qloo data."""
    title: str
    concept: str
    vibe_words: list[str]
    run_of_show: list[str]
    music: list[BaselinePick]
    venue: list[BaselinePick]
    sponsors: list[BaselinePick]
    content: list[BaselinePick]
    promo_line: str


class CompareStats(BaseModel):
    picks: int
    with_explanation: int        # picks whose reason is backed by data (Qloo scores / shared tags)
    verified_in_qloo: int        # picks that exist as Qloo entities
    venues: int
    venues_in_city: int          # venues confirmed by Qloo inside the requested city
    new_picks: int = 0           # picks that go beyond what members already named (not an echo of the input)


class BaselineResponse(BaseModel):
    baseline: BaselineBrief
    baseline_stats: CompareStats
    qloo_stats: CompareStats
    mode: Literal["llm", "mock"]
