/** Pure helpers for invite rooms: links, the copy-ready invite message, and the organizer's remembered rooms. */

export const DEMO_ROOM = { slug: 'demo', token: 'demo-room' }
export const POLL_MS = 10_000

export const joinPath = (slug: string) => `/join/${slug}`
export const organizerPath = (slug: string, token: string) => `/room/${slug}?t=${encodeURIComponent(token)}`

export function inviteMessage(o: { community: string; goal: string; city: string; url: string }): string {
  return [
    `Hey everyone! 👋 We're planning ${o.goal} for ${o.community} in ${o.city}.`,
    `Tell us what you like (about 30 seconds, no sign-up) so the plan fits all of us:`,
    o.url,
  ].join('\n')
}

export interface SavedRoom { slug: string; token: string; name: string; city: string; savedAt: number }
const KEY = 'tasteroom.rooms'
const MAX_SAVED = 5

/** Rooms this browser organised, newest first. localStorage can throw (private mode, blocked): never let that break a page. */
export function loadRooms(storage: Pick<Storage, 'getItem'> = window.localStorage): SavedRoom[] {
  try {
    const v = JSON.parse(storage.getItem(KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((r) => r && typeof r.slug === 'string' && typeof r.token === 'string') : []
  } catch { return [] }
}

export function saveRoom(room: Omit<SavedRoom, 'savedAt'>, storage: Pick<Storage, 'getItem' | 'setItem'> = window.localStorage, now = Date.now()): SavedRoom[] {
  const next = [{ ...room, savedAt: now }, ...loadRooms(storage).filter((r) => r.slug !== room.slug)].slice(0, MAX_SAVED)
  try { storage.setItem(KEY, JSON.stringify(next)) } catch { /* not persisted: the link is still on screen */ }
  return next
}

const JOINED = (slug: string) => `tasteroom.joined.${slug}`
export const joinedAs = (slug: string, storage: Pick<Storage, 'getItem'> = window.localStorage): string | null => {
  try { return storage.getItem(JOINED(slug)) } catch { return null }
}
export const markJoined = (slug: string, name: string, storage: Pick<Storage, 'setItem' | 'removeItem'> = window.localStorage) => {
  try { storage.setItem(JOINED(slug), name) } catch { /* ignore */ }
}
export const clearJoined = (slug: string, storage: Pick<Storage, 'removeItem'> = window.localStorage) => {
  try { storage.removeItem(JOINED(slug)) } catch { /* ignore */ }
}

/** "9 members responded" / "1 member responded" / "No responses yet" */
export function responseCountText(n: number): string {
  return n === 0 ? 'No responses yet' : `${n} member${n === 1 ? '' : 's'} responded`
}

/** What the organizer is told about the 15-member cap. */
export function capNote(total: number, used: number, leftOut: string[]): string | null {
  return leftOut.length ? `${total} responded. TasteRoom uses the ${used} whose tastes Qloo matched best (left out: ${leftOut.join(', ')}).` : null
}
