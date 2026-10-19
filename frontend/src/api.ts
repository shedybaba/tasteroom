import type {
  BaselineResponse, ExampleSummary, IdeasResponse, Member, PlanRequest, PlanResponse, ResolveResponse, SuggestResponse,
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
      else if (res.status === 422) message = 'Some fields need a fix: check the community, city, goal, and at least 3 members with a taste each.'
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
  resolve: (members: Member[], city: string) => call<ResolveResponse>('/api/resolve', post({ members, city })),
}
