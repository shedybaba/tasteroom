import { useEffect, useState } from 'react'
import { api } from '../api'
import { coverageCell } from '../lib/coverage'
import { useDisplay } from '../lib/display'
import type { BaselineBrief, BaselineResponse, Brief, CompareStats, PlanResponse } from '../types'
import { ErrorState, Spinner } from './ui'

type Section = 'music' | 'venue' | 'sponsors' | 'content'
const SECTIONS: { key: Section; label: string }[] = [
  { key: 'music', label: 'Music' }, { key: 'venue', label: 'Venue' },
  { key: 'sponsors', label: 'Sponsors' }, { key: 'content', label: 'Content' },
]

function StatRow({ label, a, b, aTotal, bTotal }: { label: string; a: number; b: number; aTotal: number; bTotal: number }) {
  const bar = (v: number, t: number, cls: string) => (
    <div className="mt-1 h-2 overflow-hidden rounded-full bg-ink/8"><div className={`h-full rounded-full ${cls}`} style={{ width: t ? `${(v / t) * 100}%` : '0%' }} /></div>
  )
  return (
    <div className="grid grid-cols-[1fr_1fr] gap-4 border-t border-line py-3 first:border-t-0 sm:grid-cols-[1.2fr_1fr_1fr]">
      <p className="col-span-2 text-sm font-medium sm:col-span-1">{label}</p>
      <div><p className="text-lg font-extrabold">{a}<span className="text-sm font-medium text-muted"> / {aTotal}</span></p>{bar(a, aTotal, 'bg-ink/40')}</div>
      <div><p className="text-lg font-extrabold text-accent">{b}<span className="text-sm font-medium text-muted"> / {bTotal}</span></p>{bar(b, bTotal, 'bg-accent')}</div>
    </div>
  )
}

/** Coverage can only be computed from taste data, so the LLM-only side has nothing to measure. */
function CoverageRow({ plan }: { plan: PlanResponse }) {
  const cell = coverageCell(plan.coverage)
  if (!cell) return null
  return (
    <div className="grid grid-cols-[1fr_1fr] gap-4 border-t border-line py-3 sm:grid-cols-[1.2fr_1fr_1fr]" data-testid="coverage-row-compare">
      <p className="col-span-2 text-sm font-medium sm:col-span-1">Members with a pick made for them</p>
      <div><p className="text-lg font-extrabold text-muted">n/a</p><p className="mt-1 text-xs text-muted">no taste data</p></div>
      <div><p className="text-lg font-extrabold text-accent">{cell.covered}<span className="text-sm font-medium text-muted"> / {cell.total}</span></p>
        <div className="mt-1 h-2 overflow-hidden rounded-full bg-ink/8"><div className="h-full rounded-full bg-accent" style={{ width: `${(cell.covered / cell.total) * 100}%` }} /></div></div>
    </div>
  )
}

function Column({ title, subtitle, tone, children }: { title: string; subtitle: string; tone: 'plain' | 'qloo'; children: React.ReactNode }) {
  return (
    <section className={`rounded-3xl border p-5 sm:p-6 ${tone === 'qloo' ? 'border-accent/40 bg-surface shadow-card' : 'border-line bg-surface'}`}>
      <p className={`text-xs font-bold uppercase tracking-[0.14em] ${tone === 'qloo' ? 'text-accent' : 'text-muted'}`}>{title}</p>
      <p className="mb-4 text-sm text-muted">{subtitle}</p>
      {children}
    </section>
  )
}

function ListBlock({ items }: { items: { name: string; reason: string }[] }) {
  return (
    <ul className="space-y-2">
      {items.map((p, i) => (
        <li key={i} className="text-sm"><span className="font-semibold">{p.name}</span><span className="text-ink-soft"> · {p.reason}</span></li>
      ))}
    </ul>
  )
}

function Body({ title, concept, vibe, sections }: { title: string; concept: string; vibe: string[]; sections: Record<Section, { name: string; reason: string }[]> }) {
  return (
    <>
      <h3 className="text-lg font-bold leading-snug">{title}</h3>
      <p className="mt-1 text-sm text-ink-soft">{concept}</p>
      <p className="mt-2 text-xs text-muted">Vibe: {vibe.join(', ')}</p>
      <div className="mt-4 space-y-4">
        {SECTIONS.map(({ key, label }) => sections[key].length > 0 && (
          <div key={key}><h4 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-muted">{label}</h4><ListBlock items={sections[key]} /></div>
        ))}
      </div>
    </>
  )
}

const asSections = (b: BaselineBrief | Brief): Record<Section, { name: string; reason: string }[]> => ({
  music: b.music, venue: b.venue, sponsors: b.sponsors, content: b.content,
})

const fixReasons = (s: Record<Section, { name: string; reason: string }[]>, fix: (t: string) => string) =>
  Object.fromEntries(Object.entries(s).map(([k, v]) => [k, v.map((p) => ({ ...p, reason: fix(p.reason) }))])) as typeof s

export default function CompareView({ plan, isExample = false }: { plan: PlanResponse; isExample?: boolean }) {
  const [data, setData] = useState<BaselineResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const display = useDisplay()

  useEffect(() => {
    let live = true
    // The example page has a saved comparison; every other plan (including refined versions and demo-room plans)
    // is compared by its own saved id, so the stats always describe the version on screen.
    const load = isExample ? api.exampleBaseline(plan.plan_id) : api.planBaseline(plan.plan_id)
    load.then((d) => live && setData(d)).catch((e: Error) => live && setError(e.message))
    return () => { live = false }
  }, [plan, isExample])

  if (error) return <ErrorState title="Comparison unavailable" message={error} />
  if (!data) return <Spinner label="Asking a plain LLM the same question" />

  const { baseline_stats: bs, qloo_stats: qs } = data
  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-ink-soft">
        Same community, same event goal. On the left, a language model answers from memory. On the right, the TasteRoom agent answers from Qloo’s taste data.
        A language model can name real, popular things and write well either way. But it mostly echoes what members already told it, and it can’t show <strong>why a pick suits <em>this</em> community</strong> with data behind each reason.
      </p>
      {data.mode === 'mock' && (
        <p className="rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn" role="note">
          The LLM column is a generic placeholder because no language-model key was available when this was generated.
        </p>
      )}
      <div className="rounded-3xl border border-line bg-surface p-5 sm:p-6">
        <div className="mb-1 grid grid-cols-[1fr_1fr] gap-4 sm:grid-cols-[1.2fr_1fr_1fr]">
          <p className="hidden text-xs font-bold uppercase tracking-wide text-muted sm:block">What we measured</p>
          <p className="text-xs font-bold uppercase tracking-wide text-muted">LLM only</p>
          <p className="text-xs font-bold uppercase tracking-wide text-accent">Qloo-grounded agent</p>
        </div>
        <StatRow label="Picks with a data-backed explanation" a={bs.with_explanation} aTotal={bs.picks} b={qs.with_explanation} bTotal={qs.picks} />
        <StatRow label="Picks that go beyond what members already named" a={bs.new_picks} aTotal={bs.picks} b={qs.new_picks} bTotal={qs.picks} />
        <StatRow label="Picks that exist in Qloo" a={bs.verified_in_qloo} aTotal={bs.picks} b={qs.verified_in_qloo} bTotal={qs.picks} />
        <StatRow label="Venues confirmed in your city" a={bs.venues_in_city} aTotal={bs.venues} b={qs.venues_in_city} bTotal={qs.venues} />
        <CoverageRow plan={plan} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Column title="LLM only" subtitle="No taste data. Reasons are the model’s guesses." tone="plain">
          <Body title={data.baseline.title} concept={data.baseline.concept} vibe={data.baseline.vibe_words} sections={asSections(data.baseline)} />
        </Column>
        <Column title="Qloo-grounded agent" subtitle="Every pick is a Qloo result with a reason from the data." tone="qloo">
          <Body title={plan.brief.title} concept={plan.brief.concept} vibe={plan.brief.vibe_words} sections={fixReasons(asSections(plan.brief), display)} />
        </Column>
      </div>
    </div>
  )
}

export type { CompareStats }
