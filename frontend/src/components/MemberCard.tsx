import { useState } from 'react'
import {
  KIND_OPTIONS, MAX_TASTES, SLOTS, kindFromType, tasteHint,
  type CheckState, type SlotKey, type UIMember, type UITaste,
} from '../lib/tastes'
import type { IdeasResponse, Suggestion, TasteKind } from '../types'
import Autocomplete from './Autocomplete'
import EntityImage from './EntityImage'
import Icon from './Icon'
import TasteSlot from './TasteSlot'

interface Props {
  index: number
  member: UIMember
  city: string
  ideas: Partial<Record<SlotKey, IdeasResponse>>
  /** Check-tastes result for the taste at this index (typed text only; picked tastes are matched already) */
  check: (tasteIndex: number) => CheckState
  canRemove: boolean
  onChange: (m: UIMember) => void
  onRemove: () => void
  /** 'join' = a member filling in their own card on the invite page */
  variant?: 'builder' | 'join'
  nameError?: string | null
}

const fromSuggestion = (s: Suggestion, slot: UITaste['slot']): UITaste => ({
  text: s.name, kind: kindFromType(s.type), slot, pick: s, ...(s.id ? { entity_id: s.id } : {}),
})

export default function MemberCard({ index, member, city, ideas, check, canRemove, onChange, onRemove, variant = 'builder', nameError }: Props) {
  const joining = variant === 'join'
  const [draft, setDraft] = useState('')
  const who = joining ? 'you' : member.name || `member ${index + 1}`
  const count = member.tastes.length
  const hint = tasteHint(count)
  const hasRoom = count < MAX_TASTES

  const indexOfSlot = (key: SlotKey) => member.tastes.findIndex((t) => t.slot === key)
  const put = (taste: UITaste) => {
    const i = member.tastes.findIndex((t) => t.slot === taste.slot && taste.slot !== 'extra')
    onChange({ ...member, tastes: i >= 0 ? member.tastes.map((t, j) => (j === i ? taste : t)) : [...member.tastes, taste] })
  }
  const removeAt = (i: number) => onChange({ ...member, tastes: member.tastes.filter((_, j) => j !== i) })
  const patchAt = (i: number, patch: Partial<UITaste>) =>
    onChange({ ...member, tastes: member.tastes.map((t, j) => (j === i ? { ...t, ...patch } : t)) })

  // Typing in a slot keeps the member's own words; any earlier pick is dropped because the text no longer matches it.
  const typeInto = (slot: SlotKey, kind: TasteKind) => (text: string) => {
    const i = indexOfSlot(slot)
    if (!text.trim()) return i >= 0 ? removeAt(i) : undefined
    put({ text, kind, slot })
  }
  const addExtra = (taste: UITaste) => { if (hasRoom) { onChange({ ...member, tastes: [...member.tastes, taste] }); setDraft('') } }

  return (
    <fieldset className="min-w-0 rounded-2xl border border-line bg-surface p-4 shadow-card">
      <legend className="sr-only">{joining ? 'Your picks' : `Member ${index + 1}`}</legend>
      <div className="flex items-center gap-2">
        <input aria-label={joining ? 'Your first name or nickname' : `Member ${index + 1} name`} value={member.name}
          maxLength={joining ? 24 : 60} autoComplete={joining ? 'given-name' : 'off'}
          aria-invalid={nameError ? true : undefined} aria-describedby={nameError ? `name-error-${index}` : undefined}
          placeholder={joining ? 'Your first name or a nickname' : `Name or nickname (person ${index + 1})`}
          onChange={(e) => onChange({ ...member, name: e.target.value })}
          className={`min-w-0 flex-1 rounded-lg border bg-paper px-3 py-2 text-base font-semibold placeholder:text-sm placeholder:font-normal placeholder:text-muted focus:border-ink/30 sm:text-sm ${nameError ? 'border-warn' : 'border-transparent'}`} />
        {canRemove && !joining && (
          <button type="button" onClick={onRemove} aria-label={`Remove member ${index + 1}`}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-muted hover:bg-ink/6 hover:text-ink"><Icon name="x" size={16} /></button>
        )}
      </div>

      {nameError && <p id={`name-error-${index}`} role="alert" className="mt-1 text-xs text-warn">{nameError}</p>}

      <div className="mt-3 space-y-3.5">
        {SLOTS.map((slot) => {
          const i = indexOfSlot(slot.key)
          return (
            <TasteSlot key={slot.key} slot={slot} taste={i >= 0 ? member.tastes[i] : undefined} status={i >= 0 ? check(i) : undefined}
              memberIndex={index} memberName={joining ? 'you' : member.name} city={city} ideas={ideas[slot.key]}
              onText={typeInto(slot.key, slot.kind)} onPick={(s) => put(fromSuggestion(s, slot.key))}
              onClear={() => i >= 0 && removeAt(i)} />
          )
        })}

        <div>
          <p className="mb-1 text-[13px] font-semibold leading-tight"><span aria-hidden="true" className="mr-1.5">✨</span>Anything else you love?</p>
          <ul className="space-y-2">
            {member.tastes.map((t, i) => {
              if (t.slot !== 'extra') return null
              const st = t.pick ? { name: t.pick.name, image: t.pick.image } : check(i)
              const tone = st ? 'border-ok/40 bg-ok-soft' : st === null ? 'border-warn/50 bg-warn-soft' : 'border-line bg-paper'
              return (
                <li key={i} className={`flex items-center gap-2 rounded-xl border p-1.5 pl-2 ${tone}`}>
                  {st ? <EntityImage src={st.image} name={st.name} eager className="h-8 w-8 shrink-0 rounded-md" /> : null}
                  <div className="min-w-0 flex-1">
                    {t.pick ? <p className="truncate text-sm font-medium">{t.pick.name}</p> : (
                      <input aria-label={`Extra taste ${i + 1} for ${who}`} value={t.text} maxLength={80}
                        onChange={(e) => patchAt(i, { text: e.target.value })}
                        className="w-full bg-transparent text-base font-medium focus:outline-none sm:text-sm" />
                    )}
                    {st && !t.pick && st.name.toLowerCase() !== t.text.trim().toLowerCase() && <p className="truncate text-[11px] text-ok">Matched: {st.name}</p>}
                    {t.pick && <p className="truncate text-[11px] text-ok">Matched in Qloo</p>}
                    {st === null && <p className="text-[11px] text-warn">No match: try another spelling or type</p>}
                  </div>
                  {!t.pick && (
                    <select aria-label="Kind" value={t.kind} onChange={(e) => patchAt(i, { kind: e.target.value as TasteKind })}
                      className="rounded-md border border-line bg-surface px-1.5 py-1 text-xs">
                      {KIND_OPTIONS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                    </select>
                  )}
                  <button type="button" aria-label={`Remove ${t.text}`} onClick={() => removeAt(i)}
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-muted hover:bg-ink/8"><Icon name="x" size={14} /></button>
                </li>
              )
            })}
          </ul>
          {hasRoom ? (
            <div className="mt-2 flex gap-2">
              <div className="min-w-0 flex-1">
                <Autocomplete value={draft} onChange={setDraft} type="any" city={city} placeholder="+ add something else"
                  ariaLabel={`Add something else for ${who}`} className="border-dashed bg-transparent"
                  onPick={(s) => addExtra(fromSuggestion(s, 'extra'))}
                  onSubmit={() => draft.trim() && addExtra({ text: draft.trim(), kind: 'any', slot: 'extra' })} />
              </div>
              <button type="button" onClick={() => addExtra({ text: draft.trim(), kind: 'any', slot: 'extra' })} disabled={!draft.trim()}
                className="rounded-lg bg-ink px-3 text-sm font-semibold text-paper disabled:bg-ink/25">Add</button>
            </div>
          ) : <p className="mt-2 text-xs text-muted">Maximum {MAX_TASTES} tastes per member.</p>}
        </div>
      </div>

      <p className="mt-3 text-xs text-muted" aria-live="polite">
        {hint.text}
        {hint.warn && <span className="mt-0.5 block text-warn">{hint.warn}</span>}
      </p>
    </fieldset>
  )
}
