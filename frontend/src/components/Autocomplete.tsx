import { useEffect, useId, useState } from 'react'
import { api, ApiError } from '../api'
import { typeLabel } from '../lib/format'
import type { Suggestion } from '../types'
import EntityImage from './EntityImage'

export type SuggestType = 'artist' | 'show' | 'brand' | 'podcast' | 'place' | 'any'

const DEBOUNCE_MS = 300
const MIN_CHARS = 2
const CACHE_MAX = 200

// Session cache: the same prefix is never fetched twice (the server caches Qloo for 24 h as well).
const cache = new Map<string, Suggestion[]>()
const remember = (key: string, items: Suggestion[]) => {
  if (cache.size >= CACHE_MAX) cache.delete(cache.keys().next().value as string)
  cache.set(key, items)
}

interface Result { key: string; items: Suggestion[]; note: 'busy' | 'unavailable' | null }

interface Props {
  value: string
  onChange: (text: string) => void
  onPick: (s: Suggestion) => void
  /** Enter pressed with no suggestion highlighted: the caller may commit the typed text. */
  onSubmit?: () => void
  type: SuggestType
  city: string
  placeholder: string
  ariaLabel: string
  className?: string
}

const NOTES = {
  busy: 'Lots of lookups at once. Pause a second and keep typing.',
  unavailable: 'Suggestions are unavailable right now. Type it in and we will match it later.',
  none: 'No match in Qloo yet. Keep typing, or use what you typed and we will match it when you check.',
}

/** Text input with live Qloo suggestions (WAI-ARIA combobox). Typing is never blocked: whatever is in the box is
 *  kept as the member's own words; picking a suggestion additionally pins the exact Qloo entity. */
export default function Autocomplete({ value, onChange, onPick, onSubmit, type, city, placeholder, ariaLabel, className = '' }: Props) {
  const uid = useId()
  const listId = `${uid}-list`
  const [focused, setFocused] = useState(false)
  const [result, setResult] = useState<Result | null>(null)
  const [dismissed, setDismissed] = useState<string | null>(null)
  const [active, setActive] = useState<{ key: string; i: number } | null>(null)

  const q = value.trim()
  const enabled = focused && q.length >= MIN_CHARS
  const key = `${type}|${type === 'place' || type === 'any' ? city.trim().toLowerCase() : ''}|${q.toLowerCase()}`
  const cached = cache.get(key)
  const items = cached ?? (result?.key === key ? result.items : [])
  const note = result?.key === key ? result.note : null
  const loading = enabled && cached === undefined && result?.key !== key
  const open = enabled && dismissed !== key
  const activeIndex = active?.key === key ? active.i : -1

  useEffect(() => {
    if (!enabled || cache.has(key)) return
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      api.suggest(q, type, city.trim(), ctrl.signal)
        .then((r) => {
          if (r.unavailable) return setResult({ key, items: [], note: 'unavailable' })  // not cached: may recover
          remember(key, r.results)
          setResult({ key, items: r.results, note: null })
        })
        .catch((e: unknown) => {
          if (ctrl.signal.aborted) return
          setResult({ key, items: [], note: e instanceof ApiError && e.status === 429 ? 'busy' : 'unavailable' })
        })
    }, DEBOUNCE_MS)
    return () => { clearTimeout(timer); ctrl.abort() }
  }, [enabled, key, q, type, city])

  const pick = (s: Suggestion) => { setDismissed(key); onPick(s) }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!items.length) return
      e.preventDefault()
      setDismissed(null)
      const next = e.key === 'ArrowDown' ? (activeIndex + 1) % items.length : (activeIndex <= 0 ? items.length - 1 : activeIndex - 1)
      setActive({ key, i: next })
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (open && activeIndex >= 0 && items[activeIndex]) pick(items[activeIndex])
      else { setDismissed(key); onSubmit?.() }
    } else if (e.key === 'Escape' && open) {
      e.preventDefault()
      setDismissed(key)
    }
  }

  const showPanel = open && (loading || items.length > 0 || note !== null || (cached !== undefined && cached.length === 0))
  return (
    <div className="relative">
      <input
        role="combobox" aria-label={ariaLabel} aria-autocomplete="list" aria-expanded={showPanel}
        aria-controls={listId} aria-activedescendant={activeIndex >= 0 ? `${uid}-opt-${activeIndex}` : undefined}
        autoComplete="off" autoCorrect="off" spellCheck={false} maxLength={80} value={value} placeholder={placeholder}
        onChange={(e) => { setDismissed(null); onChange(e.target.value) }} onKeyDown={onKeyDown}
        onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
        // 16px on phones: smaller text makes iOS zoom the page when the field is focused
        className={`w-full rounded-lg border border-line bg-paper px-3 py-2 text-base placeholder:text-muted focus:border-ink/40 sm:text-sm ${className}`}
      />
      {showPanel && (
        <div className="absolute inset-x-0 top-full z-30 mt-1 overflow-hidden rounded-xl border border-line bg-surface shadow-card">
          <ul id={listId} role="listbox" aria-label={`${ariaLabel} suggestions`} className="max-h-[min(18rem,45vh)] overflow-auto">
            {items.map((s, i) => (
              <li key={s.id ?? s.name} id={`${uid}-opt-${i}`} role="option" aria-selected={i === activeIndex}
                // mousedown (not click) so the input keeps focus and the panel does not close before the pick lands
                onMouseDown={(e) => { e.preventDefault(); pick(s) }} onMouseEnter={() => setActive({ key, i })}
                className={`flex cursor-pointer items-center gap-3 px-3 py-2 ${i === activeIndex ? 'bg-accent-soft' : ''}`}>
                <EntityImage src={s.image} name={s.name} eager className="h-10 w-10 shrink-0 rounded-md" />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">{s.name}</span>
                  <span className="block truncate text-xs text-muted">
                    {typeLabel(s.type)}{(s.subtitle || s.description) ? ` · ${s.subtitle ?? s.description}` : ''}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          {loading && <p role="status" className="px-3 py-2 text-xs text-muted">Searching Qloo…</p>}
          {!loading && items.length === 0 && (
            <p role="status" className="px-3 py-2 text-xs text-muted">{note ? NOTES[note] : NOTES.none}</p>
          )}
        </div>
      )}
    </div>
  )
}
