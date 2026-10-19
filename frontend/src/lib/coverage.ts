import type { Coverage, PickRef } from '../types'

export const BALANCE_INSTRUCTION = 'Balance the lineup'

/** "7 of 8 members have at least one pick made for them." Members whose fit can't be measured are named, not hidden. */
export function coverageHeadline(c: Coverage): string {
  const base = `${c.covered} of ${c.total} members ${c.total === 1 ? 'has' : 'have'} at least one pick made for them`
  return c.unmeasurable > 0 ? `${base} (${c.unmeasurable} could not be measured)` : base
}

/** A member's pull on a pick, relative to their own usual pull across the list ("1.4× their usual"). */
export const pullText = (p: PickRef): string => `${p.strength.toFixed(2).replace(/0$/, '')}× their usual`

/** Compare-tab cell: the share of members covered, or null when coverage is not measurable for this plan. */
export const coverageCell = (c: Coverage | undefined): { covered: number; total: number } | null =>
  c && c.total >= 2 ? { covered: c.covered, total: c.total } : null
