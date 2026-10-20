import type { Coverage } from '../types'

export const BALANCE_INSTRUCTION = 'Balance the lineup'

/** One line for the Brief tab. Members without a pick are named, not hidden; `show` capitalises names for display. */
export function coverageHeadline(c: Coverage, show: (name: string) => string = (n) => n): string {
  if (c.covered === c.total && c.unmeasurable === 0) return 'Every member has a pick made for them.'
  const left = c.members.filter((m) => !m.covered).map((m) => show(m.member))
  const base = `${c.covered} of ${c.total} members ${c.covered === 1 ? 'has' : 'have'} a pick made for them`
  const unm = c.unmeasurable > 0 ? ` (${c.unmeasurable} could not be measured)` : ''
  return `${base}${unm}.${left.length ? ` Not yet: ${left.join(', ')}.` : ''}`
}

/** Compare-tab cell: members covered, and what kind of pick covered them; null when coverage is not measurable for this plan. */
export const coverageCell = (c: Coverage | undefined): { covered: number; total: number; standout: number; personal: number } | null =>
  c && c.total >= 2 ? { covered: c.covered, total: c.total, standout: c.standout, personal: c.personal } : null
