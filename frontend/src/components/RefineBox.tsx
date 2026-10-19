import { useState } from 'react'
import { QUICK_REFINEMENTS } from '../lib/refine'
import Icon from './Icon'
import { Button } from './ui'

interface Props { busy: boolean; error: string | null; onRun: (instruction: string) => void }

/** "Tell the agent what to change": free text or one tap. The agent re-queries only what the change affects. */
export default function RefineBox({ busy, error, onRun }: Props) {
  const [text, setText] = useState('')
  // Open on tablets and desktops; collapsed on phones so it does not push the brief a screen and a half down.
  const [open, setOpen] = useState(() => window.matchMedia('(min-width: 640px)').matches)
  const submit = (value: string) => { const v = value.trim(); if (v.length >= 3 && !busy) onRun(v) }
  return (
    <details open={open || !!error || busy} onToggle={(e) => setOpen(e.currentTarget.open)}
      className="group mt-6 rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5" aria-labelledby="refine-h">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 [&::-webkit-details-marker]:hidden">
        <h2 id="refine-h" className="flex items-center gap-2 text-base font-extrabold"><Icon name="spark" size={18} className="text-accent" />Tell the agent what to change</h2>
        <Icon name="down" size={18} className="shrink-0 text-muted transition-transform group-open:rotate-180" />
      </summary>
      <p className="mt-0.5 text-sm text-muted">It re-queries only what the change affects and keeps the rest of your plan. Each change is saved as a new version.</p>
      <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); submit(text) }}>
        <input aria-label="What should the agent change?" value={text} maxLength={200} disabled={busy} onChange={(e) => setText(e.target.value)}
          placeholder="e.g. a cheaper venue, more chill music, somewhere closer to the beach"
          className="min-w-0 flex-1 rounded-xl border border-line bg-paper px-4 py-2.5 text-base placeholder:text-muted focus:border-ink/40 sm:text-sm" />
        <Button type="submit" disabled={busy || text.trim().length < 3}>Refine <Icon name="arrow" size={16} /></Button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Quick changes">
        {QUICK_REFINEMENTS.map((q) => (
          <button key={q} type="button" disabled={busy} onClick={() => onRun(q)}
            className="rounded-full border border-line bg-paper px-3 py-1 text-sm font-medium hover:border-ink/40 disabled:opacity-50">{q}</button>
        ))}
      </div>
      {error && <p role="alert" className="mt-3 flex gap-2 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn"><Icon name="alert" size={18} className="mt-0.5 shrink-0" />{error}</p>}
    </details>
  )
}
