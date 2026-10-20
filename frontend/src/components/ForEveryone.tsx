import { inLineup, personalForDomain, personalRow } from '../lib/personal'
import type { PlanResponse } from '../types'
import PersonalCard from './PersonalCard'

const MISSING = 'rounded-2xl border border-dashed border-line bg-surface p-3 text-sm text-muted'

/** "Something for everyone": one personal pick per member. On the Brief tab each member shows their best (music first);
 *  on a domain tab it shows the picks in that domain. Members with none are listed with the reason, never hidden. */
export default function ForEveryone({ plan, domain }: { plan: PlanResponse; domain?: 'music' | 'content' }) {
  const rows = domain ? null : personalRow(plan)
  const d = domain ? personalForDomain(plan, domain) : null
  const nothing = domain ? d!.picks.length === 0 && d!.missing.length === 0 : (plan.personal ?? []).length === 0 && (plan.personal_skipped ?? []).length === 0
  if (nothing) return null   // mock data, or a plan saved before personal picks existed
  return (
    <section aria-labelledby={`fe-${domain ?? 'brief'}`} data-testid="for-everyone" className="mt-10">
      <h2 id={`fe-${domain ?? 'brief'}`} className="text-sm font-bold uppercase tracking-[0.12em] text-muted">Something for everyone</h2>
      <p className="mt-1 max-w-3xl text-sm text-ink-soft">
        One pick per member, found by asking Qloo what that person would like from their own tastes alone. Each one also fits the group:
        it is one of the group&rsquo;s results, or Qloo ties it to the group within 5% of the average pick.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {domain
          ? d!.picks.map((p) => <PersonalCard key={`${p.member}-${p.entity.id}`} pick={p} inLineup={inLineup(plan, p)} />)
          : rows!.filter((r) => r.pick).map((r) => <PersonalCard key={r.member} pick={r.pick!} inLineup={inLineup(plan, r.pick!)} />)}
        {domain
          ? d!.missing.map((s) => <p key={s.member} className={MISSING} data-testid="personal-missing"><strong className="text-ink">{s.member}</strong>: {s.note}</p>)
          : rows!.filter((r) => !r.pick).map((r) => <p key={r.member} className={MISSING} data-testid="personal-missing"><strong className="text-ink">{r.member}</strong>: {r.missing}</p>)}
      </div>
    </section>
  )
}
