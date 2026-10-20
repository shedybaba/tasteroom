import type { Coverage, PickRef } from '../types'

export const BALANCE_INSTRUCTION = 'Balance the lineup'

/** "7 of 8 members have at least one pick made for them." Members whose fit can't be measured are named, not hidden. */
export function coverageHeadline(c: Coverage): string {
  const base = `${c.covered} of ${c.total} members ${c.total === 1 ? 'has' : 'have'} at least one pick made for them`
  return c.unmeasurable > 0 ? `${base} (${c.unmeasurable} could not be measured)` : base
}

/** The two kinds of pick that count are kept apart, so the strict "stands out" number is never blurred into the headline. */
export function coverageBreakdown(c: Coverage): string {
  return `${c.standout} with a pick that stands out in the lineup · ${c.personal} with a personal pick · ${c.in_lineup} already in the main lineup`
}

/** A member's pull on a standout pick, relative to their own usual pull across the list ("1.4× their usual"). */
export const pullText = (p: PickRef): string => (p.strength == null ? '' : `${p.strength.toFixed(2).replace(/0$/, '')}× their usual`)

/** Compare-tab cell: members covered, and what kind of pick covered them; null when coverage is not measurable for this plan. */
export const coverageCell = (c: Coverage | undefined): { covered: number; total: number; standout: number; personal: number } | null =>
  c && c.total >= 2 ? { covered: c.covered, total: c.total, standout: c.standout, personal: c.personal } : null
