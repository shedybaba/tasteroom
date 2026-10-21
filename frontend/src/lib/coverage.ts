import type { Coverage } from '../types'

export const BALANCE_INSTRUCTION = 'Balance the lineup'

/** Compare-tab cell: members covered, and what kind of pick covered them; null when coverage is not measurable for this plan. */
export const coverageCell = (c: Coverage | undefined): { covered: number; total: number; standout: number; personal: number } | null =>
  c && c.total >= 2 ? { covered: c.covered, total: c.total, standout: c.standout, personal: c.personal } : null
