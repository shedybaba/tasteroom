import type { PersonalPick, PersonalSkip, PlanResponse } from '../types'

export const personalLabel = (member: string): string => `Personal pick for ${member}`

export interface RowItem { member: string; pick: PersonalPick | null; missing: string | null }

/** One entry per member, in the organizer's order: their music pick, else their show/podcast pick, else why they have none. */
export function personalRow(plan: PlanResponse): RowItem[] {
  const picks = plan.personal ?? []
  const skips = plan.personal_skipped ?? []
  return plan.request.members.map(({ name }) => {
    const pick = picks.find((p) => p.member === name && p.domain === 'music') ?? picks.find((p) => p.member === name) ?? null
    const why = skips.find((s) => s.member === name)
    return { member: name, pick, missing: pick ? null : (why?.note ?? 'No personal pick could be made for them.') }
  })
}

/** A domain tab's "Something for everyone" row: the members' picks in that domain, and who has none there (with the reason). */
export function personalForDomain(plan: PlanResponse, domain: 'music' | 'content'): { picks: PersonalPick[]; missing: PersonalSkip[] } {
  const members = plan.request.members.map((m) => m.name)
  const picks = (plan.personal ?? []).filter((p) => p.domain === domain).sort((a, b) => members.indexOf(a.member) - members.indexOf(b.member))
  const missing = (plan.personal_skipped ?? []).filter((s) => s.domain === domain)
  return { picks, missing }
}

/** Is this personal pick already one of the brief's main picks? */
export function inLineup(plan: PlanResponse, pick: PersonalPick): boolean {
  const b = plan.brief
  return [...b.music, ...b.venue, ...b.sponsors, ...b.content].some((p) => p.entity_id === pick.entity.id)
}
