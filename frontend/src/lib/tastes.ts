import type { Member, Suggestion, Taste, TasteKind } from '../types'

export const KIND_OPTIONS: { value: TasteKind; label: string }[] = [
  { value: 'any', label: 'Any' }, { value: 'artist', label: 'Artist' }, { value: 'tv_show', label: 'Show' },
  { value: 'movie', label: 'Movie' }, { value: 'brand', label: 'Brand' }, { value: 'place', label: 'Place' },
  { value: 'podcast', label: 'Podcast' }, { value: 'video_game', label: 'Game' }, { value: 'book', label: 'Book' },
]
export const MAX_TASTES = 6
export const MIN_MEMBERS = 3
export const MAX_MEMBERS = 15

/** What a chip needs to show a match: the Qloo name and thumbnail. */
export interface Matched { name: string; image: string | null }
/** undefined = not checked yet, null = no match, otherwise matched */
export type CheckState = Matched | null | undefined

// ---- guided slots -------------------------------------------------------------------------------

export type SlotKey = 'artist' | 'show' | 'brand' | 'podcast' | 'place'
export type TasteSlot = SlotKey | 'extra'

export interface SlotDef { key: SlotKey; emoji: string; label: string; placeholder: string; kind: TasteKind }
export const SLOTS: SlotDef[] = [
  { key: 'artist', emoji: '🎵', label: 'An artist you have on repeat', placeholder: 'Start typing an artist', kind: 'artist' },
  { key: 'show', emoji: '📺', label: "A show or movie you'd rewatch", placeholder: 'Start typing a show or movie', kind: 'tv_show' },
  { key: 'brand', emoji: '🛍️', label: 'A brand you actually buy', placeholder: 'Start typing a brand', kind: 'brand' },
  { key: 'podcast', emoji: '🎧', label: 'A podcast you listen to', placeholder: 'Start typing a podcast', kind: 'podcast' },
  { key: 'place', emoji: '📍', label: 'A spot you love hanging out at', placeholder: 'Start typing a café, bar or park', kind: 'place' },
]
export const GUIDED_TARGET = SLOTS.length

/** A taste in the Builder: the API's Taste plus where it sits in the card and, if the member picked a
 *  Qloo suggestion, that suggestion (so the chip is already matched and the id skips re-resolution). */
export interface UITaste extends Taste { slot: TasteSlot; pick?: Suggestion }
export interface UIMember { name: string; tastes: UITaste[] }

export function kindFromType(urn: string): TasteKind {
  const t = urn.split(':').pop() ?? ''
  const map: Record<string, TasteKind> = {
    artist: 'artist', tv_show: 'tv_show', movie: 'movie', brand: 'brand', podcast: 'podcast', place: 'place',
    videogame: 'video_game', video_game: 'video_game', book: 'book',
  }
  return map[t] ?? 'any'
}

export function slotForKind(kind: TasteKind): SlotKey | null {
  switch (kind) {
    case 'artist': return 'artist'
    case 'tv_show': case 'movie': return 'show'
    case 'brand': return 'brand'
    case 'podcast': return 'podcast'
    case 'place': return 'place'
    default: return null
  }
}

/** Put existing tastes (from an example or a pasted list) into the guided slots by kind; a second taste of the
 *  same kind, and kinds with no slot ("any", games, books), go to the free "add something else" area. */
export function assignSlots(tastes: Taste[]): UITaste[] {
  const used = new Set<SlotKey>()
  return tastes.map((t) => {
    const slot = slotForKind(t.kind)
    if (slot && !used.has(slot)) { used.add(slot); return { ...t, slot } }
    return { ...t, slot: 'extra' as const }
  })
}

export const toUIMember = (m: Member): UIMember => ({ name: m.name, tastes: assignSlots(m.tastes) })

/** The API's view of a member: picked suggestions carry their Qloo id; UI-only fields are dropped. */
export function toRequestMember(m: UIMember, name: string): Member {
  return {
    name,
    tastes: m.tastes.filter((t) => t.text.trim()).map((t) => ({
      text: t.text.trim(), kind: t.kind, ...(t.pick?.id ? { entity_id: t.pick.id } : {}),
    })),
  }
}

export function tasteHint(count: number): { text: string; warn: string | null } {
  return {
    text: count > GUIDED_TARGET ? `${count} added: more variety = better picks` : `${count} of ${GUIDED_TARGET} added: more variety = better picks`,
    warn: count < 2 ? 'Add at least 2 so there is something to match. You can still continue.' : null,
  }
}

/** The idea chips to show for one member: a rotating window over the fetched list, so members filling their
 *  cards one after another are not all offered the same four. */
export function ideasFor<T>(list: T[], memberIndex: number, count = 4): T[] {
  if (list.length <= count) return list
  const start = (memberIndex * count) % list.length
  return Array.from({ length: count }, (_, i) => list[(start + i) % list.length])
}

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
