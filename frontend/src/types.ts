// Mirrors backend/app/models.py. Keep in sync.

export type TasteKind =
  | 'any' | 'artist' | 'tv_show' | 'movie' | 'brand' | 'place' | 'podcast' | 'book' | 'video_game'

export interface Taste { text: string; kind: TasteKind; entity_id?: string }
export interface Member { name: string; tastes: Taste[] }

export interface PlanOptions {
  hidden_gems: boolean
  price_level_max: number | null
  day: string | null
  venue_kind: string | null
}

export interface PlanRequest {
  community_name: string
  city: string
  event_goal: string
  members: Member[]
  options: PlanOptions
}

export interface SlimEntity {
  id: string
  name: string
  type: string
  popularity: number | null
  description: string | null
  image: string | null
  address: string | null
  city: string | null
  neighborhood?: string | null
  neighborhood_id?: string | null
  website: string | null
  price_level?: number | null   // Qloo's price level for a venue (1 cheapest to 4); null/absent = Qloo has no price
  tags: string[]
  tag_ids: string[]
  affinity: number | null
  explain: Record<string, number>
}

export interface ResolvedTaste { member: string; input: string; entity: SlimEntity | null; lookup_failed?: boolean }
export interface Contribution { member: string; score: number; via: string[] }

export type Domain = 'music' | 'venues' | 'brands' | 'content'

export interface Recommendation {
  entity: SlimEntity
  domain: Domain
  why: Contribution[]
  shared_tags: string[]
  explanation_method: 'qloo_explainability' | 'per_member_affinity' | 'tag_overlap'
}

export interface TraceStep {
  step: number; tool: string; args: Record<string, unknown>; inferred?: string[]; refined?: string[]; summary: string; ms: number; ok: boolean
}

export interface BriefPick { entity_id: string; name: string; reason: string }
export interface Brief {
  title: string
  concept: string
  vibe_words: string[]
  run_of_show: string[]
  music: BriefPick[]
  venue: BriefPick[]
  sponsors: BriefPick[]
  content: BriefPick[]
  promo_line: string
}

export type PlanMode = 'agent' | 'pipeline' | 'precomputed' | 'mock'

export interface PlanResponse {
  plan_id: string
  request: PlanRequest
  resolved: ResolvedTaste[]
  locality: SlimEntity | null
  recommendations: Partial<Record<Domain, Recommendation[]>>
  brief: Brief
  trace: TraceStep[]
  mode: PlanMode
  warnings: string[]
  dropped_picks: number
  parent_id?: string | null
  root_id?: string | null
  version?: number
  refinement?: Refinement | null
  coverage?: Coverage
  venue_choice?: VenueChoice
  can_undo?: boolean
  personal?: PersonalPick[]
  personal_skipped?: PersonalSkip[]
}

export interface VenueChoice { top_id: string | null; cheapest_id: string | null; top_is_cheapest: boolean; cheapest_level: number | null; priced: number; total: number }

export interface PickRef { domain: Domain; entity_id: string; name: string; kind: 'standout' | 'personal'; strength: number | null }
export interface Swap { member: string; add: PickRef; drop: PickRef | null }
export interface MemberCoverage {
  member: string; covered: boolean; picks: PickRef[]; personal: PickRef | null; in_lineup: boolean; note: string | null; suggestion: Swap | null
}
export interface Coverage {
  members: MemberCoverage[]; covered: number; standout: number; personal: number; in_lineup: number; total: number; unmeasurable: number; balance: Swap[]
}

export interface PersonalPick {
  member: string; domain: 'music' | 'content'; entity: SlimEntity; via: string[]; member_rank: number
  fit: 'in_group_results' | 'group_affinity'; group_rank: number | null; group_ratio: number | null; explanation: string
}
export interface PersonalSkip { member: string; domain: 'music' | 'content'; reason: 'no_signal' | 'none_fit_group' | 'qloo_error'; note: string }

export interface DiscordEmbed { title: string; description: string; url?: string; fields: { name: string; value: string }[]; footer: { text: string } }
export interface DiscordPayload { username: string; content: string; embeds: DiscordEmbed[] }

export interface Change { domain: Domain; swapped: number; of: number; note: string | null }
export interface Refinement { instruction: string; trace_start: number; changes: Change[] }

export interface ResolveResponse { resolved: ResolvedTaste[]; locality: SlimEntity | null }

export interface BaselinePick { name: string; reason: string }
export interface BaselineBrief {
  title: string
  concept: string
  vibe_words: string[]
  run_of_show: string[]
  music: BaselinePick[]
  venue: BaselinePick[]
  sponsors: BaselinePick[]
  content: BaselinePick[]
  promo_line: string
}
export interface CompareStats {
  picks: number
  with_explanation: number
  verified_in_qloo: number
  venues: number
  venues_in_city: number
  new_picks: number
}
export interface BaselineResponse {
  baseline: BaselineBrief
  baseline_stats: CompareStats
  qloo_stats: CompareStats
  mode: 'llm' | 'mock'
}

export interface ExampleSummary {
  id: string
  name: string
  city: string
  goal: string
  tagline: string
  members: { name: string; tastes: string[] }[]
  request: PlanRequest
}

/** A Qloo entity offered by autocomplete or as an idea (id is null for static fallback ideas). */
export interface Suggestion {
  id: string | null
  name: string
  type: string
  image: string | null
  description: string | null
  subtitle: string | null
}
export interface SuggestResponse { results: Suggestion[]; unavailable?: boolean }
export interface IdeasResponse { type: string; source: 'qloo' | 'static' | 'none'; ideas: Suggestion[]; needs_city: boolean }

// ---- invite rooms ----
export interface RoomInfo { slug: string; community_name: string; city: string; event_goal: string; response_count: number; demo: boolean }
export interface CreatedRoom { slug: string; organizer_token: string; join_path: string; organizer_path: string }
export interface RoomTaste { text: string; kind: TasteKind; entity_id?: string; name?: string; image?: string | null; type?: string }
export interface RoomResponse { id: number; name: string; created_at: string; matched: number; tastes: RoomTaste[] }
export interface RoomResponses {
  room: RoomInfo
  responses: RoomResponse[]
  plan: { will_use: number; left_out: string[]; cap: number; min: number }
}
