import { useState } from 'react'
import { KIND_OPTIONS, MAX_TASTES } from '../lib/tastes'
import type { CheckState } from '../lib/tastes'
import type { Member, TasteKind } from '../types'
import EntityImage from './EntityImage'
import Icon from './Icon'

interface Props {
  index: number
  member: Member
  check: (tasteIndex: number) => CheckState
  canRemove: boolean
  onChange: (m: Member) => void
  onRemove: () => void
}

export default function MemberCard({ index, member, check, canRemove, onChange, onRemove }: Props) {
  const [draft, setDraft] = useState('')

  function addTaste() {
    const text = draft.trim()
    if (!text || member.tastes.length >= MAX_TASTES) return
    onChange({ ...member, tastes: [...member.tastes, { text, kind: 'any' }] })
    setDraft('')
  }
  const patchTaste = (i: number, patch: Partial<Member['tastes'][number]>) =>
    onChange({ ...member, tastes: member.tastes.map((t, j) => (j === i ? { ...t, ...patch } : t)) })

  return (
    <fieldset className="rounded-2xl border border-line bg-surface p-4 shadow-card">
      <legend className="sr-only">Member {index + 1}</legend>
      <div className="flex items-center gap-2">
        <input aria-label={`Member ${index + 1} name`} value={member.name} maxLength={60} placeholder={`Member ${index + 1}`}
          onChange={(e) => onChange({ ...member, name: e.target.value })}
          className="min-w-0 flex-1 rounded-lg border border-transparent bg-paper px-3 py-2 font-semibold placeholder:font-normal placeholder:text-muted focus:border-ink/30" />
        {canRemove && (
          <button type="button" onClick={onRemove} aria-label={`Remove member ${index + 1}`}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-muted hover:bg-ink/6 hover:text-ink"><Icon name="x" size={16} /></button>
        )}
      </div>

      <ul className="mt-3 space-y-2">
        {member.tastes.map((t, i) => {
          const st = check(i)
          const tone = st ? 'border-ok/40 bg-ok-soft' : st === null ? 'border-warn/50 bg-warn-soft' : 'border-line bg-paper'
          return (
            <li key={i} className={`flex items-center gap-2 rounded-xl border p-1.5 pl-2 ${tone}`}>
              {st ? <EntityImage src={st.image} name={st.name} className="h-8 w-8 shrink-0 rounded-md" /> : null}
              <div className="min-w-0 flex-1">
                <input aria-label={`Taste ${i + 1} for ${member.name || `member ${index + 1}`}`} value={t.text} maxLength={80}
                  onChange={(e) => patchTaste(i, { text: e.target.value })}
                  className="w-full bg-transparent text-sm font-medium focus:outline-none" />
                {st && st.name.toLowerCase() !== t.text.trim().toLowerCase() && <p className="truncate text-[11px] text-ok">Matched: {st.name}</p>}
                {st === null && <p className="text-[11px] text-warn">No match: try another spelling or type</p>}
              </div>
              <select aria-label="Kind" value={t.kind} onChange={(e) => patchTaste(i, { kind: e.target.value as TasteKind })}
                className="rounded-md border border-line bg-surface px-1.5 py-1 text-xs">
                {KIND_OPTIONS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
              </select>
              <button type="button" aria-label={`Remove ${t.text}`} onClick={() => onChange({ ...member, tastes: member.tastes.filter((_, j) => j !== i) })}
                className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-muted hover:bg-ink/8"><Icon name="x" size={14} /></button>
            </li>
          )
        })}
      </ul>

      {member.tastes.length < MAX_TASTES ? (
        <div className="mt-2 flex gap-2">
          <input aria-label={`Add a taste for ${member.name || `member ${index + 1}`}`} value={draft} maxLength={80}
            onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTaste() } }}
            placeholder="Add an artist, show, brand, place…"
            className="min-w-0 flex-1 rounded-lg border border-dashed border-line bg-transparent px-3 py-2 text-sm placeholder:text-muted focus:border-ink/40" />
          <button type="button" onClick={addTaste} disabled={!draft.trim()}
            className="rounded-lg bg-ink px-3 text-sm font-semibold text-paper disabled:bg-ink/25">Add</button>
        </div>
      ) : <p className="mt-2 text-xs text-muted">Maximum {MAX_TASTES} tastes per member.</p>}
    </fieldset>
  )
}
