import { typeLabel } from '../lib/format'
import { useDisplay } from '../lib/display'
import { personalLabel } from '../lib/personal'
import type { PersonalPick } from '../types'
import EntityImage from './EntityImage'

/** One member's personal pick: a Qloo result found from their own tastes alone that also fits the group. The text is the
 *  server's own explanation (built from Qloo's data), never free-form. */
export default function PersonalCard({ pick, inLineup = false }: { pick: PersonalPick; inLineup?: boolean }) {
  const display = useDisplay()
  const e = pick.entity
  return (
    <article className="flex gap-3 rounded-2xl border border-line bg-surface p-3" data-testid="personal-card" data-member={pick.member}>
      <EntityImage src={e.image} name={e.name} className="h-20 w-20 shrink-0 rounded-xl" />
      <div className="min-w-0">
        <p className="text-xs font-bold uppercase tracking-wide text-accent">{personalLabel(pick.member)}</p>
        <h3 className="font-bold leading-snug">{e.name}
          <span className="ml-2 text-xs font-medium text-muted">{typeLabel(e.type)}{inLineup ? ' · in the lineup' : ''}</span>
        </h3>
        <p className="mt-1 text-sm text-ink-soft">{display(pick.explanation)}</p>
      </div>
    </article>
  )
}
