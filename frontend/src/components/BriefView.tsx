import type { Brief, BriefPick, PlanResponse, SlimEntity } from '../types'
import { useDisplay } from '../lib/display'
import { briefToMarkdown } from '../lib/format'
import CopyButton from './CopyButton'
import BalanceButton from './BalanceButton'
import ForEveryone from './ForEveryone'
import EntityImage from './EntityImage'
import { personalMembers } from '../lib/personal'
import { priceText, venueLabel } from '../lib/venues'
import PersonalBadge from './PersonalBadge'
import { Chip } from './ui'

function Picks({ title, picks, entities, plan, domain }: { title: string; picks: BriefPick[]; entities: Map<string, SlimEntity>; plan: PlanResponse; domain?: 'music' | 'content' }) {
  const display = useDisplay()
  if (!picks.length) return null
  return (
    <section>
      <h3 className="mb-3 text-sm font-bold uppercase tracking-[0.12em] text-muted">{title}</h3>
      {title === 'Venue' && plan.venue_choice?.cheapest_id === null && (
        <p className="-mt-1 mb-3 text-sm text-ink-soft" data-testid="cheapest-unavailable">Cheapest option: Price not available for these venues.</p>
      )}
      <ul className="grid gap-3 sm:grid-cols-2">
        {picks.map((p) => {
          const e = entities.get(p.entity_id)
          const mine = domain ? personalMembers(plan, domain, p.entity_id) : []
          return (
            <li key={p.entity_id} className="flex gap-3 rounded-2xl border border-line bg-surface p-3">
              <EntityImage src={e?.image ?? null} name={p.name} className="h-16 w-16 shrink-0 rounded-xl" />
              <div className="min-w-0">
                <p className="font-bold leading-snug">{p.name}{title === 'Venue' && <span className="ml-2 rounded-full bg-accent-soft px-2 py-0.5 text-xs font-bold text-accent" data-testid="venue-tag">{venueLabel(plan.venue_choice, p.entity_id) ?? 'Backup'}</span>}</p>
                {mine.length > 0 && <p className="mt-1"><PersonalBadge members={mine} /></p>}
                <p className="mt-0.5 text-sm text-ink-soft">{display(p.reason)}</p>
                {title === 'Venue' && <p className="mt-0.5 text-xs font-medium text-muted" data-testid="venue-price">{priceText(e?.price_level)}</p>}
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

export default function BriefView({ plan, balancing = false, balanceError = null, onBalance }: {
  plan: PlanResponse; balancing?: boolean; balanceError?: string | null; onBalance?: () => void
}) {
  const b: Brief = plan.brief
  const entities = new Map<string, SlimEntity>()
  Object.values(plan.recommendations).forEach((recs) => recs?.forEach((r) => entities.set(r.entity.id, r.entity)))
  const display = useDisplay()
  const md = briefToMarkdown(plan, display)

  return (
    <div className="space-y-8">
      <div className="rounded-3xl bg-night p-6 text-paper sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-accent">The concept</p>
            <h2 className="mt-2 text-lg font-semibold leading-snug sm:text-2xl sm:font-bold">{display(b.concept)}</h2>
          </div>
          <CopyButton text={md} label="Copy brief as Markdown" />
        </div>
        <div className="mt-5 flex flex-wrap gap-2" aria-label="Vibe">
          {b.vibe_words.map((v) => <Chip key={v} tone="dark">{v}</Chip>)}
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_1.4fr]">
        <section>
          <h3 className="mb-3 text-sm font-bold uppercase tracking-[0.12em] text-muted">Run of show</h3>
          <ol className="space-y-3">
            {b.run_of_show.map((line, i) => (
              <li key={i} className="flex gap-3">
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold text-accent">{i + 1}</span>
                <span className="text-ink-soft">{display(line)}</span>
              </li>
            ))}
          </ol>
          <div className="mt-8 rounded-2xl border border-dashed border-line bg-surface p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-muted">Announcement for Discord / X</p>
            <p className="mt-2 font-medium">{display(b.promo_line)}</p>
            <div className="mt-3"><CopyButton text={display(b.promo_line)} label="Copy announcement" /></div>
          </div>
        </section>
        <div className="space-y-7">
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-accent">Crowd-pleasers</p>
          <Picks title="Music" picks={b.music} entities={entities} plan={plan} domain="music" />
          <Picks title="Venue" picks={b.venue} entities={entities} plan={plan} />
          <Picks title="Sponsors" picks={b.sponsors} entities={entities} plan={plan} />
          <Picks title="Content" picks={b.content} entities={entities} plan={plan} domain="content" />
        </div>
      </div>
      <ForEveryone plan={plan} footer={onBalance && (plan.coverage?.balance.length ?? 0) > 0 ? <BalanceButton busy={balancing} error={balanceError} onBalance={onBalance} /> : undefined} />
      {plan.dropped_picks > 0 && (
        <p className="text-xs text-muted">{plan.dropped_picks} AI-suggested pick(s) that Qloo did not return were removed.</p>
      )}
    </div>
  )
}
