// Mirrors backend/app/models.py. Keep in sync.

export type TasteKind =
  | 'any' | 'artist' | 'tv_show' | 'movie' | 'brand' | 'place' | 'podcast' | 'book' | 'video_game'

export interface Taste { text: string; kind: TasteKind }
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
  website: string | null
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
  step: number; tool: string; args: Record<string, unknown>; summary: string; ms: number; ok: boolean
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
}

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
