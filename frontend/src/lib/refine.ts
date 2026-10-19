import type { Change, Refinement } from '../types'
import { DOMAIN_META } from './format'

/** One tap each. These map cleanly onto what the agent can do with Qloo (price, popularity, tags, neighbourhoods, content). */
export const QUICK_REFINEMENTS = [
  'Cheaper venue',
  'More hidden gems',
  'Swap the music vibe: more chill',
  'Add a watch-party content theme',
  'Different neighbourhood',
]

export const REFINE_STEPS = [
  'Reading your request',
  'Working out which parts of the plan it affects',
  'Re-querying only those in Qloo',
  'Rewriting the brief around the change',
  'Checking every pick against Qloo',
]

/** "Venues: 3 swapped" (+ what was applied). Zero swaps is said plainly rather than hidden. */
export function changeText(c: Change): string {
  const label = DOMAIN_META[c.domain].label
  return c.swapped === 0 ? `${label}: re-checked, same picks` : `${label}: ${c.swapped} swapped`
}

export const changeLine = (r: Refinement): string =>
  r.changes.map((c) => (c.note ? `${changeText(c)} (${c.note})` : changeText(c))).join(' · ')

export const versionLabel = (v: { version: number; example: boolean }) => `v${v.version}${v.example ? ' (example)' : ''}`
