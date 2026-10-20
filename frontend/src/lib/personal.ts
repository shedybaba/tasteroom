import type { PersonalPick, PersonalSkip, PlanResponse, Recommendation } from '../types'

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

const DOMAIN_WORDS = { music: 'music', content: 'shows and podcasts' } as const

/** Up to three of the member's tastes; a third one that would make the line long is left out so the card stays one short line. */
export function shortTastes(via: string[]): string[] {
  const two = via.slice(0, 2)
  const third = via[2]
  return third && two.join(', ').length + third.length <= 36 ? [...two, third] : two
}

/** The one line on a personal card: whose tastes it came from. `show` capitalises the member's name for display. */
export function personalLine(p: PersonalPick, show: (name: string) => string = (n) => n): string {
  const tastes = shortTastes(p.via).join(', ')
  return `Picked from ${show(p.member)}'s tastes${tastes ? `: ${tastes}` : ''}. Fits the group too.`
}

/** The numbers behind a personal pick (kept out of the card until "Why?" is opened). */
export function personalDetail(p: PersonalPick, show: (name: string) => string = (n) => n): string[] {
  const own = `Qloo's #${p.member_rank} result for ${show(p.member)}'s tastes on their own.`
  const fit = p.fit === 'in_group_results' && p.group_rank
    ? `It is #${p.group_rank} in the group's ${DOMAIN_WORDS[p.domain]} results.`
    : p.group_ratio != null && p.group_ratio >= 1
      ? "Qloo ties it to the group as strongly as the group's average pick."
      : `Qloo ties it to the group at ${Math.round((p.group_ratio ?? 0) * 100)}% of the group's average pull.`
  return [own, fit]
}

/** The members whose personal pick this entity is (usually one). Used to badge the lineup row and the tab card. */
export function personalMembers(plan: PlanResponse, domain: string, entityId: string): string[] {
  return (plan.personal ?? []).filter((p) => p.domain === domain && p.entity.id === entityId).map((p) => p.member)
}

/** What the group data adds beyond the member it was chosen for: who else it stands out for, or that it is a crowd-pleaser; null when
 *  there is nothing true to add. Mirrors backend attribution.group_sentence, so the tab card and the brief row agree. */
export function personalFit(rec: Recommendation | undefined, members: string[], standOut = 1.15): string | null {
  if (!rec || rec.why.length < 2) return null
  const n = rec.why.length
  const others = [...rec.why].sort((a, b) => b.score - a.score).filter((c) => c.score * n >= standOut && !members.includes(c.member)).map((c) => c.member)
  if (others.length) return `Also stands out for ${others.slice(0, 2).join(' and ')}`
  return rec.why.some((c) => c.score * n >= standOut) ? null : `A crowd-pleaser: fits all ${n} members`
}

/** The tab card's line for a personal pick: led by the member, then the group data if it says something. */
export function personalCardSummary(rec: Recommendation, members: string[], show: (name: string) => string = (n) => n): string {
  const lead = `Personal pick for ${members.map(show).join(' and ')}`
  const fit = personalFit(rec, members)
  return fit ? `${lead}. ${fit}` : lead
}
