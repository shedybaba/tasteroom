import type { Recommendation } from '../types'
import { useDisplay, useMemberName } from '../lib/display'
import { METHOD_LABEL, pct } from '../lib/format'

/** Per-member contribution bars. The backend compares each member's pull on this pick with their usual
 *  pull across the list (Qloo's raw scores are near-uniform, so raw percentages would mislead). The bar
 *  fills to 50% at an even share (the tick); longer means that member's tastes pull harder here. */
export default function WhyPanel({ rec }: { rec: Recommendation }) {
  const n = rec.why.length
  const display = useDisplay()
  const name = useMemberName()
  return (
    <div className="mt-3 rounded-xl bg-paper p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-wide text-muted">Why this pick</span>
        <span className="rounded-full bg-ink/6 px-2 py-0.5 text-[11px] font-medium text-ink-soft">{METHOD_LABEL[rec.explanation_method]}</span>
      </div>
      {n > 0 ? (
        <ul className="space-y-2">
          {rec.why.slice(0, 6).map((c) => {
            const fill = Math.min(100, c.score * n * 50)
            return (
              <li key={c.member}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{name(c.member)}</span>
                  <span className="text-xs text-muted">{pct(c.score)} of the pull</span>
                </div>
                <div className="relative mt-1 h-2 overflow-hidden rounded-full bg-ink/8"
                  role="img" aria-label={`${name(c.member)}: ${pct(c.score)} of the pull`}>
                  <div className="h-full rounded-full bg-accent" style={{ width: `${fill}%` }} />
                  <div className="absolute inset-y-0 left-1/2 w-px bg-ink/40" />
                </div>
                {c.via.length > 0 && <p className="mt-0.5 text-xs text-muted">via {display(c.via.join(', '))}</p>}
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="text-muted">No member-level data for this pick; it is shown for the shared tags below.</p>
      )}
      {n > 1 && <p className="mt-2 text-[11px] text-muted">Bars compare each member’s pull on this pick with their usual pull across the list. At the tick, this pick suits them as much as the others; past it, it suits them more.</p>}
      {rec.shared_tags.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted">Shared tags</span>
          {rec.shared_tags.map((t) => <span key={t} className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">{t}</span>)}
        </div>
      )}
    </div>
  )
}
