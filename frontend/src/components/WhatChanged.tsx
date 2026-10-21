import { changeText } from '../lib/refine'
import type { Refinement } from '../types'
import Icon from './Icon'

/** The "What changed" strip shown on a refined version. */
export default function WhatChanged({ refinement, onUndo, undoing = false, undoError = null }: {
  refinement: Refinement; onUndo?: () => void; undoing?: boolean; undoError?: string | null
}) {
  return (
    <section aria-label="What changed" className="mt-6 rounded-2xl border border-accent/30 bg-accent-soft/50 p-4 sm:p-5">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-accent">What changed</p>
      <p className="mt-1 flex items-start gap-2 font-semibold"><Icon name="spark" size={18} className="mt-0.5 shrink-0 text-accent" />
        <span>You asked: &ldquo;{refinement.instruction}&rdquo;</span></p>
      <ul className="mt-3 flex flex-wrap gap-2" data-testid="changes">
        {refinement.changes.map((c) => (
          <li key={c.domain} className="rounded-full border border-accent/30 bg-surface px-3 py-1 text-sm">
            <span className="font-semibold">{changeText(c)}</span>
            {c.note && <span className="text-muted"> · {c.note}</span>}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">Everything else in the plan is exactly as it was. The agent steps are under &ldquo;How it worked&rdquo;.</p>
      {onUndo && (
        <p className="mt-2 text-sm">
          <button type="button" onClick={onUndo} disabled={undoing} data-testid="undo-button"
            className="font-semibold text-accent underline underline-offset-4 hover:text-ink disabled:opacity-50">{undoing ? 'Undoing…' : 'Undo last change'}</button>
        </p>
      )}
      {undoError && <p role="alert" className="mt-2 text-sm text-warn">{undoError}</p>}
    </section>
  )
}
