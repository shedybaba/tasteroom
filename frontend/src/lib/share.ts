import type { PlanResponse } from '../types'

/** Path of the public, read-only view of a plan. Saved examples already have one; every other plan gets `?shared=1`. */
export const sharePath = (planId: string, isExample: boolean): string => (isExample ? `/example/${planId}` : `/plan/${planId}?shared=1`)

// Same rule as backend/app/discord.py (the server re-checks it): only a real Discord webhook URL is accepted.
const WEBHOOK = /^https:\/\/(?:(?:canary|ptb)\.)?(?:discord|discordapp)\.com\/api(?:\/v\d+)?\/webhooks\/\d{15,25}\/[A-Za-z0-9_-]{20,120}\/?$/
export const isWebhookUrl = (url: string): boolean => WEBHOOK.test(url.trim())

// Some Qloo addresses are a long single segment; a poll line should stay short.
const clip = (text: string | undefined, max = 40): string | null => (!text ? null : text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`)

export interface PollVenue { name: string; where: string | null }

/** The top 3 venues: the brief's own picks first, then the next-ranked Qloo venues if the brief has fewer than 3. */
export function pollVenues(plan: PlanResponse): PollVenue[] {
  const ranked = plan.recommendations.venues ?? []
  const byId = new Map(ranked.map((r) => [r.entity.id, r.entity]))
  const ids = [...plan.brief.venue.map((v) => v.entity_id), ...ranked.map((r) => r.entity.id)]
  const out: PollVenue[] = []
  for (const id of [...new Set(ids)]) {
    const e = byId.get(id)
    const name = e?.name ?? plan.brief.venue.find((v) => v.entity_id === id)?.name
    if (!name) continue
    out.push({ name, where: e?.neighborhood ?? clip(e?.address?.split(',')[0]?.trim()) })
    if (out.length === 3) break
  }
  return out
}

const NUMBERS = ['1️⃣', '2️⃣', '3️⃣']

/** Ready-to-paste Discord poll: members vote by reacting with a number. Null when there is nothing to vote between. */
export function pollText(plan: PlanResponse): string | null {
  const venues = pollVenues(plan)
  if (venues.length < 2) return null
  return [
    `📍 Where should we hold ${plan.brief.title}? Vote with a reaction:`,
    '',
    ...venues.map((v, i) => `${NUMBERS[i]} ${v.name}${v.where ? ` (${v.where})` : ''}`),
    '',
    `Picked from Qloo taste data for ${plan.request.community_name}.`,
  ].join('\n')
}
