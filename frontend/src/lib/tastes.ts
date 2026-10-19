import type { Member, SlimEntity, Taste, TasteKind } from '../types'

export const KIND_OPTIONS: { value: TasteKind; label: string }[] = [
  { value: 'any', label: 'Any' }, { value: 'artist', label: 'Artist' }, { value: 'tv_show', label: 'Show' },
  { value: 'movie', label: 'Movie' }, { value: 'brand', label: 'Brand' }, { value: 'place', label: 'Place' },
  { value: 'podcast', label: 'Podcast' }, { value: 'video_game', label: 'Game' }, { value: 'book', label: 'Book' },
]
export const MAX_TASTES = 6
export const MIN_MEMBERS = 3
export const MAX_MEMBERS = 15

/** undefined = not checked yet, null = no match, entity = matched */
export type CheckState = SlimEntity | null | undefined

/** "Ada: Burna Boy, Nike" per line -> members (kind left as "any" so Qloo picks the best match). */
export function parsePasted(text: string): Member[] {
  return text.split('\n').map((l) => l.trim()).filter(Boolean).slice(0, MAX_MEMBERS).map((line, i) => {
    const [head, ...rest] = line.split(':')
    const hasName = rest.length > 0
    const tastes: Taste[] = (hasName ? rest.join(':') : head).split(/[,;]/).map((t) => t.trim()).filter(Boolean)
      .slice(0, MAX_TASTES).map((text) => ({ text, kind: 'any' }))
    return { name: hasName ? head.trim() : `Member ${i + 1}`, tastes }
  }).filter((m) => m.tastes.length > 0)
}
