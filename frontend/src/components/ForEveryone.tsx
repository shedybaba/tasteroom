import { useMemberName } from '../lib/display'
import { inLineup, personalForDomain, personalRow } from '../lib/personal'
import type { PlanResponse } from '../types'
import PersonalCard from './PersonalCard'

const MISSING = 'rounded-2xl border border-dashed border-line bg-surface p-3 text-sm text-muted'

/** "Something for everyone": one personal pick per member. On the Brief tab each member shows their best (music first);
 *  on a domain tab it shows the picks in that domain. Members with none are listed with the reason, never hidden. */
export default function ForEveryone({ plan, domain, footer }: { plan: PlanResponse; domain?: 'music' | 'content'; footer?: React.ReactNode }) {
  const name = useMemberName()
  const rows = domain ? null : personalRow(plan)
  const d = domain ? personalForDomain(plan, domain) : null
  const nothing = domain ? d!.picks.length === 0 && d!.missing.length === 0 : (plan.personal ?? []).length === 0 && (plan.personal_skipped ?? []).length === 0
  if (nothing) return null   // mock data, or a plan saved before personal picks existed
  return (
    <section aria-labelledby={`fe-${domain ?? 'brief'}`} data-testid="for-everyone" className="mt-10">
      <h2 id={`fe-${domain ?? 'brief'}`} className="text-sm font-bold uppercase tracking-[0.12em] text-muted">Something for everyone</h2>
      <p className="mt-1 text-sm text-ink-soft">One pick per member, made from their own tastes.</p>
      <details className="mt-1 text-sm" data-testid="how-picked">
        <summary className="inline-flex min-h-8 cursor-pointer select-none items-center font-semibold text-ink underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-ink">How are these picked?</summary>
        <div className="mt-2 max-w-3xl space-y-2 text-ink-soft">
          <p>
            For each member, Qloo is asked what they would like from their own tastes alone. We keep their highest-ranked new result that also fits
            the group: it is one of the group&rsquo;s results, or Qloo ties it to the group within 5% of the group&rsquo;s average pull.
            (&ldquo;Pull&rdquo; is how strongly Qloo links a pick to someone&rsquo;s tastes.)
          </p>
          <p>
            A pick <strong>stands out</strong> for a member only when their pull on it is at least 15% above their usual level, the same bar as
            the &ldquo;Why this pick&rdquo; panel. Most crowd-pleasers don&rsquo;t, so the Compare tab counts both kinds separately.
          </p>
        </div>
      </details>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {domain
          ? d!.picks.map((p) => <PersonalCard key={`${p.member}-${p.entity.id}`} pick={p} inLineup={inLineup(plan, p)} />)
          : rows!.filter((r) => r.pick).map((r) => <PersonalCard key={r.member} pick={r.pick!} inLineup={inLineup(plan, r.pick!)} />)}
        {domain
          ? d!.missing.map((s) => <p key={s.member} className={MISSING} data-testid="personal-missing"><strong className="text-ink">{name(s.member)}</strong>: {s.note}</p>)
          : rows!.filter((r) => !r.pick).map((r) => <p key={r.member} className={MISSING} data-testid="personal-missing"><strong className="text-ink">{name(r.member)}</strong>: {r.missing}</p>)}
      </div>
      {footer}
    </section>
  )
}
