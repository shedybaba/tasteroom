import { typeLabel } from '../lib/format'
import { useDisplay, useMemberName } from '../lib/display'
import { personalDetail, personalLabel, personalLine } from '../lib/personal'
import type { PersonalPick } from '../types'
import EntityImage from './EntityImage'

/** One member's personal pick: a Qloo result found from their own tastes alone that also fits the group. The line is built from
 *  Qloo's data (which of their tastes it came from); the numbers (rank, fit) sit behind "Why?". */
export default function PersonalCard({ pick, inLineup = false }: { pick: PersonalPick; inLineup?: boolean }) {
  const display = useDisplay()
  const name = useMemberName()
  const e = pick.entity
  return (
    <article className="flex gap-3 rounded-2xl border border-line bg-surface p-3" data-testid="personal-card" data-member={pick.member}>
      <EntityImage src={e.image} name={e.name} className="h-20 w-20 shrink-0 rounded-xl" />
      <div className="min-w-0">
        <p className="text-xs font-bold uppercase tracking-wide text-accent">{personalLabel(name(pick.member))}</p>
        <h3 className="font-bold leading-snug">{e.name}
          <span className="ml-2 text-xs font-medium text-muted">{typeLabel(e.type)}{inLineup ? ' · in the lineup' : ''}</span>
        </h3>
        <p className="mt-1 text-sm text-ink-soft" data-testid="personal-line">{display(personalLine(pick, name))}</p>
        <details className="group mt-1 text-xs" data-testid="personal-why">
          <summary className="inline-flex min-h-6 cursor-pointer select-none items-center font-semibold text-ink underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ink">Why?</summary>
          <ul className="mt-1 space-y-0.5 text-muted">
            {personalDetail(pick, name).map((line) => <li key={line}>{display(line)}</li>)}
          </ul>
        </details>
      </div>
    </article>
  )
}
