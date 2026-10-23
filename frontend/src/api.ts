import type {
  BaselineResponse, CreatedRoom, DiscordPayload, ExampleSummary, IdeasResponse, Member, PlanRequest, PlanResponse, ResolveResponse,
  RoomInfo, RoomResponses, SlackPayload, SuggestResponse,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }
  if (!res.ok) {
    let message = 'Something went wrong. Please try again.'
    try {
      const body = await res.json()
      if (typeof body?.error === 'string') message = body.error
      else if (res.status === 422) message = 'Some fields need a fix: check the group name, city, plan, and at least 3 people with a taste each.'
    } catch { /* keep default */ }
    throw new ApiError(res.status, message)
  }
  return res.json() as Promise<T>
}

const post = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  examples: () => call<ExampleSummary[]>('/api/examples'),
  examplePlan: (id: string) => call<PlanResponse>(`/api/examples/${id}/plan`),
  exampleBaseline: (id: string) => call<BaselineResponse>(`/api/examples/${id}/baseline`),
  plan: (req: PlanRequest) => call<PlanResponse>('/api/plan', post(req)),
  getPlan: (id: string) => call<PlanResponse>(`/api/plan/${id}`),
  baseline: (req: PlanRequest) => call<BaselineResponse>('/api/baseline', post(req)),
  suggest: (q: string, type: string, city: string, signal?: AbortSignal) =>
    call<SuggestResponse>(`/api/suggest?${new URLSearchParams({ q, type, city })}`, { signal }),
  ideas: (type: string, city: string) => call<IdeasResponse>(`/api/ideas?${new URLSearchParams({ type, city })}`),
  refine: (planId: string, instruction: string) =>
    call<PlanResponse>(`/api/plan/${encodeURIComponent(planId)}/refine`, post({ instruction })),
  announcement: (planId: string) => call<{ payload: DiscordPayload }>(`/api/plan/${encodeURIComponent(planId)}/announcement`),
  slackAnnouncement: (planId: string) => call<{ payload: SlackPayload }>(`/api/plan/${encodeURIComponent(planId)}/announcement?service=slack`),
  // The webhook URL is a credential: it goes in the POST body (never a URL), is used once and is not kept anywhere.
  postToDiscord: (planId: string, webhookUrl: string) =>
    call<{ ok: boolean }>(`/api/plan/${encodeURIComponent(planId)}/discord`, post({ webhook_url: webhookUrl })),
  postToSlack: (planId: string, webhookUrl: string) =>
    call<{ ok: boolean }>(`/api/plan/${encodeURIComponent(planId)}/slack`, post({ webhook_url: webhookUrl })),
  undo: (planId: string) => call<PlanResponse>(`/api/plan/${encodeURIComponent(planId)}/undo`, { method: 'POST' }),
  planBaseline: (planId: string) => call<BaselineResponse>(`/api/plan/${encodeURIComponent(planId)}/baseline`, { method: 'POST' }),
  createRoom: (body: { community_name: string; city: string; event_goal: string }) => call<CreatedRoom>('/api/rooms', post(body)),
  roomInfo: (slug: string) => call<RoomInfo>(`/api/rooms/${encodeURIComponent(slug)}`),
  joinRoom: (slug: string, member: Member) =>
    call<{ ok: boolean; count: number }>(`/api/rooms/${encodeURIComponent(slug)}/join`, post({ member_name: member.name, tastes: member.tastes })),
  // The organizer token travels in a header, never in a URL that servers and proxies might log.
  roomResponses: (slug: string, token: string, signal?: AbortSignal) =>
    call<RoomResponses>(`/api/rooms/${encodeURIComponent(slug)}/responses`, { headers: { 'X-Organizer-Token': token }, signal }),
  removeResponse: (slug: string, token: string, id: number) =>
    call<{ ok: boolean }>(`/api/rooms/${encodeURIComponent(slug)}/responses/${id}`, { method: 'DELETE', headers: { 'X-Organizer-Token': token } }),
  roomPlan: (slug: string, token: string) =>
    call<PlanResponse>(`/api/rooms/${encodeURIComponent(slug)}/plan`, { method: 'POST', headers: { 'X-Organizer-Token': token } }),
  resolve: (members: Member[], city: string) => call<ResolveResponse>('/api/resolve', post({ members, city })),
}
