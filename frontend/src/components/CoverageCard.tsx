import { coverageHeadline, pullText } from '../lib/coverage'
import { DOMAIN_META } from '../lib/format'
import type { Coverage, MemberCoverage } from '../types'
import Icon from './Icon'
import { Button } from './ui'

function Row({ m }: { m: MemberCoverage }) {
  const s = m.suggestion
  return (
    <li className="flex gap-3 border-t border-line py-3 first:border-t-0" data-testid="coverage-row" data-covered={m.covered}>
      <span className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-white ${m.covered ? 'bg-ok' : 'bg-warn'}`} aria-hidden="true">
        <Icon name={m.covered ? 'check' : 'alert'} size={12} />
      </span>
      <div className="min-w-0 text-sm">
        <p className="font-semibold">
          {m.member}
          <span className="sr-only">{m.covered ? ': has picks that stand out for them' : ': nothing stands out for them yet'}</span>
        </p>
        {m.covered && (
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {m.picks.slice(0, 4).map((p) => (
              <li key={p.entity_id} className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs">
                <span className="font-semibold">{p.name}</span> <span className="text-muted">· {pullText(p)}</span>
              </li>
            ))}
          </ul>
        )}
        {!m.covered && s && (
          <p className="mt-0.5 text-ink-soft" data-testid="coverage-suggestion">
            {m.member} has nothing that stands out yet <span aria-hidden="true">→</span> <span className="sr-only">suggestion: </span>
            Swap in <strong>{s.add.name}</strong>
            <span className="text-muted"> ({DOMAIN_META[s.add.domain].tab.toLowerCase()}, {pullText(s.add)}{s.drop ? `, replacing ${s.drop.name}` : ', room in the list'})</span>
          </p>
        )}
        {!m.covered && !s && m.note && <p className="mt-0.5 text-muted">{m.note}</p>}
      </div>
    </li>
  )
}

/** "Something for everyone": which members have a pick that stands out for them, what would cover the rest, and a
 *  one-click "Balance the lineup" that applies those swaps (existing Qloo results only). */
export default function CoverageCard({ coverage, busy, error, onBalance }: {
  coverage: Coverage; busy: boolean; error: string | null; onBalance?: () => void   // no onBalance = read-only (shared view)
}) {
  if (coverage.total < 2) return null
  const swaps = coverage.balance.length
  const pct = Math.round((coverage.covered / coverage.total) * 100)
  return (
    <section aria-labelledby="coverage-title" className="rounded-3xl border border-line bg-surface p-5 sm:p-6" data-testid="coverage-card">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-accent">Coverage</p>
      <h3 id="coverage-title" className="mt-1 text-xl font-extrabold leading-snug sm:text-2xl" data-testid="coverage-score">{coverageHeadline(coverage)}</h3>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-ink/8" role="img" aria-label={`${pct}% of measurable members covered`}>
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-3 max-w-3xl text-sm text-ink-soft">
        A pick is &ldquo;made for&rdquo; a member when their pull on it is at least 15% above their usual level (the same bar as the bars in the Why panel).
        The other picks are crowd-pleasers: they fit the whole group without standing out for one person.
      </p>
      <ul className="mt-4">{coverage.members.map((m) => <Row key={m.member} m={m} />)}</ul>
      {onBalance && <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
        {swaps > 0 ? (
          <>
            <Button onClick={onBalance} disabled={busy} data-testid="balance-button">
              {busy ? 'Balancing the lineup…' : `Balance the lineup (${swaps} ${swaps === 1 ? 'swap' : 'swaps'})`}
            </Button>
            <p className="max-w-xl text-xs text-muted">Swaps in the picks above, taken from the Qloo results already on this plan (no new search), then rewrites the brief. Saved as a new version.</p>
          </>
        ) : (
          <p className="text-sm text-muted" data-testid="balance-none">
            {coverage.covered === coverage.total ? 'Everyone has a pick made for them.' : 'No further swaps are possible: none of Qloo’s results for this plan stands out for the remaining members.'}
          </p>
        )}
      </div>}
      {error && <p role="alert" className="mt-3 text-sm text-warn">{error}</p>}
    </section>
  )
}
