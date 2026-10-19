import { ideasFor, type CheckState, type SlotDef, type UITaste } from '../lib/tastes'
import { typeLabel } from '../lib/format'
import type { IdeasResponse, Suggestion } from '../types'
import Autocomplete from './Autocomplete'
import EntityImage from './EntityImage'
import Icon from './Icon'

interface Props {
  slot: SlotDef
  taste: UITaste | undefined
  /** Result of "Check tastes" for typed (not picked) text */
  status: CheckState
  memberIndex: number
  memberName: string
  city: string
  ideas: IdeasResponse | undefined
  onText: (text: string) => void
  onPick: (s: Suggestion) => void
  onClear: () => void
}

/** One guided prompt ("An artist you have on repeat"): optional, with live Qloo autocomplete and "Need ideas?" chips. */
export default function TasteSlot({ slot, taste, status, memberIndex, memberName, city, ideas, onText, onPick, onClear }: Props) {
  const who = memberName || `member ${memberIndex + 1}`
  const picked = taste?.pick
  const empty = !taste
  const chips = ideas && ideas.ideas.length ? ideasFor(ideas.ideas, memberIndex) : []

  return (
    <div>
      <p className="mb-1 text-[13px] font-semibold leading-tight">
        <span aria-hidden="true" className="mr-1.5">{slot.emoji}</span>{slot.label}
      </p>

      {picked ? (
        <div className="flex items-center gap-2.5 rounded-xl border border-ok/40 bg-ok-soft p-1.5 pr-2">
          <EntityImage src={picked.image} name={picked.name} eager className="h-9 w-9 shrink-0 rounded-md" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold">{picked.name}</span>
            <span className="block truncate text-[11px] text-ok">Matched in Qloo · {typeLabel(picked.type)}</span>
          </span>
          <button type="button" onClick={onClear} aria-label={`Clear ${picked.name} for ${who}`}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-muted hover:bg-ink/8 hover:text-ink">
            <Icon name="x" size={16} />
          </button>
        </div>
      ) : (
        <>
          <Autocomplete
            value={taste?.text ?? ''} onChange={onText} onPick={onPick} type={slot.key} city={city}
            placeholder={slot.placeholder} ariaLabel={`${slot.label} (${who})`}
            className={status ? 'border-ok/40 bg-ok-soft' : status === null ? 'border-warn/50 bg-warn-soft' : ''}
          />
          {status && <p className="mt-0.5 truncate text-[11px] text-ok">Matched: {status.name}</p>}
          {status === null && <p className="mt-0.5 text-[11px] text-warn">No match: try another spelling, or pick a suggestion</p>}
        </>
      )}

      {empty && (
        slot.key === 'place' && ideas?.needs_city ? (
          <p className="mt-1 text-[11px] text-muted">Add the event city above to see local spots.</p>
        ) : slot.key === 'place' && !ideas ? (
          <p className="mt-1 text-[11px] text-muted" role="status">Looking for popular spots in {city.trim()}…</p>
        ) : chips.length > 0 && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5" role="group" aria-label={`Ideas: ${slot.label}`}>
            <span className="text-[11px] font-medium text-muted">Need ideas?</span>
            {chips.map((idea) => (
              <button key={idea.id ?? idea.name} type="button" onClick={() => onPick(idea)}
                className="inline-flex max-w-full items-center gap-1 rounded-full border border-line bg-surface py-0.5 pl-1 pr-2.5 text-xs font-medium hover:border-ink/40">
                {idea.image
                  ? <EntityImage src={idea.image} name={idea.name} eager className="h-5 w-5 shrink-0 rounded-full" />
                  : <Icon name="plus" size={12} className="ml-1 shrink-0" />}
                <span className="truncate">{idea.name}</span>
              </button>
            ))}
          </div>
        )
      )}
    </div>
  )
}
