import { useEffect, useState } from 'react'
import { api } from '../api'
import type { IdeasResponse } from '../types'
import type { SlotKey } from './tastes'

/** Static names used only if the ideas route itself cannot be reached (the backend has its own fallback). */
const STATIC: Record<Exclude<SlotKey, 'place'>, [string, string][]> = {
  artist: [['Burna Boy', 'artist'], ['Beyoncé', 'artist'], ['Drake', 'artist'], ['Taylor Swift', 'artist'], ['Wizkid', 'artist'], ['Rihanna', 'artist']],
  show: [['Stranger Things', 'tv_show'], ['Money Heist', 'tv_show'], ['The Office', 'tv_show'], ['Squid Game', 'tv_show'], ['Inception', 'movie'], ['Black Mirror', 'tv_show']],
  brand: [['Nike', 'brand'], ['Apple', 'brand'], ['Adidas', 'brand'], ['Spotify', 'brand'], ['Netflix', 'brand'], ['Zara', 'brand']],
  podcast: [['Call Her Daddy', 'podcast'], ['The Joe Rogan Experience', 'podcast'], ['Crime Junkie', 'podcast'], ['The Daily', 'podcast'], ['Huberman Lab', 'podcast'], ['How I Built This', 'podcast']],
}

const fallback = (slot: SlotKey): IdeasResponse => slot === 'place'
  ? { type: slot, source: 'none', ideas: [], needs_city: false }
  : { type: slot, source: 'static', needs_city: false,
      ideas: STATIC[slot].map(([name, t]) => ({ id: null, name, type: `urn:entity:${t}`, image: null, description: null, subtitle: null })) }

const NEEDS_CITY: IdeasResponse = { type: 'place', source: 'none', ideas: [], needs_city: true }
const CITY_DEBOUNCE_MS = 900

/** "Need ideas?" chips. Artist, show, brand and podcast ideas load once per page load; venue ideas need the
 *  event city, so they load when a city has been typed (after a pause) and again if it changes. */
export function useIdeas(city: string): Partial<Record<SlotKey, IdeasResponse>> {
  const [loaded, setLoaded] = useState<Partial<Record<SlotKey, IdeasResponse>>>({})
  const trimmed = city.trim()

  useEffect(() => {
    let live = true
    ;(['artist', 'show', 'brand', 'podcast'] as const).forEach((slot) => {
      api.ideas(slot, '').then((r) => live && setLoaded((p) => ({ ...p, [slot]: r })))
        .catch(() => live && setLoaded((p) => ({ ...p, [slot]: fallback(slot) })))
    })
    return () => { live = false }
  }, [])

  useEffect(() => {
    if (trimmed.length < 2) return
    let live = true
    const timer = setTimeout(() => {
      api.ideas('place', trimmed).then((r) => live && setLoaded((p) => ({ ...p, place: r })))
        .catch(() => live && setLoaded((p) => ({ ...p, place: fallback('place') })))
    }, CITY_DEBOUNCE_MS)
    return () => { live = false; clearTimeout(timer) }
  }, [trimmed])

  return { ...loaded, place: trimmed.length < 2 ? NEEDS_CITY : loaded.place }
}
