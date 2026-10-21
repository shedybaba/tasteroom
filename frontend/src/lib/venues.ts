import type { PlanResponse, Recommendation, VenueChoice } from '../types'

/** "Price level 2 of 4 ($$)", or exactly "Price not available": a price is never guessed. */
export const priceText = (level?: number | null): string => (level ? `Price level ${level} of 4 (${'$'.repeat(level)})` : 'Price not available')

/** The label a venue carries in the brief and on the Venues tab, or null for an ordinary backup. */
export function venueLabel(choice: VenueChoice | undefined, entityId: string): string | null {
  if (!choice) return null
  const top = choice.top_id === entityId
  const cheapest = choice.cheapest_id === entityId
  return top && cheapest ? 'Top pick · Cheapest option' : top ? 'Top pick' : cheapest ? 'Cheapest option' : null
}

/** The Venues tab: top pick first, the cheapest option next, then the remaining venues (backups) in Qloo's order. */
export function orderVenues(plan: PlanResponse): Recommendation[] {
  const recs = plan.recommendations.venues ?? []
  const c = plan.venue_choice
  if (!c) return recs
  const first = [c.top_id, c.cheapest_id].filter((id, i, a): id is string => !!id && a.indexOf(id) === i)
  const pinned = first.map((id) => recs.find((r) => r.entity.id === id)).filter((r): r is Recommendation => !!r)
  return [...pinned, ...recs.filter((r) => !pinned.includes(r))]
}
