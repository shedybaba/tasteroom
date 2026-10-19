import { createContext, useContext } from 'react'
import type { ResolvedTaste } from '../types'

/** Qloo's name -> the member's own spelling, for entities that differ only by case ("TEms" -> "Tems"). */
export type DisplayMap = Map<string, string>

export function buildDisplayMap(resolved: ResolvedTaste[]): DisplayMap {
  const map: DisplayMap = new Map()
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
