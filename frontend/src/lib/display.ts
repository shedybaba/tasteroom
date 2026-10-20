import { createContext, useContext } from 'react'
import type { ResolvedTaste } from '../types'

/** Text as stored -> text as shown: Qloo's name -> the member's own spelling for entities that differ only by case
 *  ("TEms" -> "Tems"), and a member's name -> the same name capitalised ("kelechi" -> "Kelechi"). Stored text is never changed. */
export type DisplayMap = Map<string, string>

/** "kelechi obi" -> "Kelechi Obi", "o'brien" -> "O'Brien". Only the first letter of each part is raised; the rest is kept as typed. */
export const capName = (name: string): string => name.replace(/(^|[\s'-])(\p{L})/gu, (_, sep: string, c: string) => sep + c.toUpperCase())

/** Lowercase names that are also ordinary English words: replacing them inside a sentence ("this will fit") would corrupt the
 *  text, so those are capitalised only where a name is shown on its own (labels, headings), never inside prose. */
const WORD_NAMES = new Set(['will', 'may', 'mark', 'grace', 'joy', 'hope', 'faith', 'rose', 'bill', 'art', 'pat', 'sue', 'ray', 'dawn', 'summer', 'april', 'jack', 'rich', 'earnest', 'frank', 'max', 'sky', 'bay', 'bob', 'don', 'gene', 'guy', 'jay', 'lane', 'miles', 'page', 'pearl', 'ruby', 'sage', 'wade'])

export function buildDisplayMap(resolved: ResolvedTaste[], memberNames: string[] = []): DisplayMap {
  const map: DisplayMap = new Map()
  for (const raw of memberNames) {
    const name = raw.trim()
    if (name && capName(name) !== name && !WORD_NAMES.has(name.toLowerCase())) map.set(name, capName(name))
  }
  for (const r of resolved) {
    const typed = r.input.trim()
    const qloo = r.entity?.name
    if (qloo && typed && typed !== qloo && typed.toLowerCase() === qloo.toLowerCase() && !map.has(qloo)) map.set(qloo, typed)
  }
  return map
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Swap Qloo's spelling for the member's own wherever it appears as a whole word in a text. */
export function applyDisplay(text: string, map: DisplayMap): string {
  let out = text
  for (const [qloo, typed] of map) out = out.replace(new RegExp(`(?<![\\w])${escape(qloo)}(?![\\w])`, 'g'), typed)
  return out
}

/** The name to show for a matched taste: the member's spelling if it only differs by case. */
export function shownName(input: string, qlooName: string): string {
  const typed = input.trim()
  return typed && typed.toLowerCase() === qlooName.toLowerCase() ? typed : qlooName
}

export const DisplayContext = createContext<DisplayMap>(new Map())
export const useDisplay = () => {
  const map = useContext(DisplayContext)
  return (text: string) => applyDisplay(text, map)
}

/** A member's name on its own (a label, a heading): always capitalised, whatever the stored spelling. */
export const useMemberName = () => (name: string) => capName(name)
