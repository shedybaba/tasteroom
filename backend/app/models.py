"""Pydantic models (BUILD_PLAN.md section 6). Mirrored in frontend/src/types.ts."""
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class Taste(BaseModel):
    text: str = Field(max_length=80)
    # Set when the member picked a Qloo suggestion: resolution then fetches this entity directly (no search).
    entity_id: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f-]{36}$")
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
    neighborhood: str | None = None      # properties.locality.neighborhood (places): "Ikoyi", "Maroko"...
    neighborhood_id: str | None = None   # that neighbourhood's Qloo locality id, usable as filter.location
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
    lookup_failed: bool = False  # True = Qloo errored/was busy (not "no such entity"): worth retrying


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
    args: dict            # the arguments actually applied (never filters the organizer did not set)
    inferred: list[str] = []  # names in `args` that came from the event goal rather than the form
    refined: list[str] = []   # names in `args` that came from the organizer's refinement request
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


class Change(BaseModel):
    domain: Literal["music", "venues", "brands", "content"]
    swapped: int          # brief picks in this section that are new in this version
    of: int               # picks in the section
    note: str | None = None   # what was applied: "hidden gems on", "price <= 2", "area: Ikoyi", "tag: Mellow"


class Refinement(BaseModel):
    instruction: str
    trace_start: int      # index in `trace` where this refinement's steps begin (earlier steps belong to the parent run)
    changes: list[Change]


class PickRef(BaseModel):
    domain: Literal["music", "venues", "brands", "content"]
    entity_id: str
    name: str
    kind: Literal["standout", "personal"] = "standout"
    strength: float | None = None   # standout: the member's pull in multiples of an even share (1.0 = average); personal: None


class Swap(BaseModel):
    member: str
    add: PickRef                 # a Qloo result that is not in the brief yet but stands out for the member
    drop: PickRef | None = None  # the brief pick it would replace (None = the section had room)


class MemberCoverage(BaseModel):
    member: str
    covered: bool                    # a brief pick stands out for them, or they have a personal pick
    picks: list[PickRef] = []        # the brief picks that stand out for them (strict rule), strongest first
    personal: PickRef | None = None  # their personal pick (found from their own tastes), if any
    in_lineup: bool = False          # a standout or personal pick for them is in the main lineup (the brief's sections)
    note: str | None = None          # why there is nothing to show or suggest
    suggestion: Swap | None = None   # not in the lineup yet: the personal pick (or standout result) that would put them there


class Coverage(BaseModel):
    members: list[MemberCoverage]
    covered: int                     # members with a standout pick OR a personal pick
    standout: int = 0                # of those, members with a pick that stands out in the lineup (the strict rule)
    personal: int = 0                # members with a personal pick
    in_lineup: int = 0               # members with a standout or personal pick in the main lineup
    total: int                       # members whose fit can be measured (at least one taste matched in Qloo)
    unmeasurable: int = 0
    balance: list[Swap] = []         # what "Balance the lineup" would change


class PersonalPick(BaseModel):
    """A Qloo result found from ONE member's own tastes (a query seeded only by them) that also fits the group."""
    member: str
    domain: Literal["music", "content"]
    entity: SlimEntity
    via: list[str] = []                     # the member's own tastes behind it (Qloo's explainability for their query)
    member_rank: int                        # 1 = first result for their tastes alone
    fit: Literal["in_group_results", "group_affinity"]
    group_rank: int | None = None           # fit == in_group_results: its position in the group's results
    group_ratio: float | None = None        # its group-level affinity divided by the group's average (when known)
    explanation: str                        # built from the fields above; never free text from the LLM


class PersonalSkip(BaseModel):
    member: str
    domain: Literal["music", "content"]
    reason: Literal["no_signal", "none_fit_group", "qloo_error"]
    note: str


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
    # Versions: a refinement is saved as a new plan whose parent is the plan that was refined.
    parent_id: str | None = None
    root_id: str | None = None   # the first plan of the family (None on the first plan itself)
    version: int = 1
    refinement: Refinement | None = None
    personal: list[PersonalPick] = []            # one per member per domain (music, content) where one was found
    personal_skipped: list[PersonalSkip] = []    # members with none, and why

    @computed_field  # type: ignore[prop-decorator]
    @property
    def coverage(self) -> Coverage:
        """Derived from the explanation data on every serialisation, so saved plans and examples get it too."""
        from .coverage import compute  # local import: coverage.py builds on these models
        return compute(self)


class DiscordPost(BaseModel):
    webhook_url: str = Field(max_length=300)


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


class RefineRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=200)
