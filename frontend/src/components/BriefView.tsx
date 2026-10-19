import { useState } from 'react'
import type { Brief, BriefPick, PlanResponse, SlimEntity } from '../types'
import { briefToMarkdown, copyText } from '../lib/format'
import EntityImage from './EntityImage'
import Icon from './Icon'
import { Button, Chip } from './ui'

function CopyButton({ text, label, variant = 'ghost' }: { text: string; label: string; variant?: 'ghost' | 'dark' }) {
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle')
  async function go() {
    setState((await copyText(text)) ? 'ok' : 'fail')
    setTimeout(() => setState('idle'), 2000)
  }
  return (
    <Button type="button" variant={variant} onClick={go} aria-live="polite">
      <Icon name={state === 'ok' ? 'check' : 'copy'} size={16} />
      {state === 'ok' ? 'Copied' : state === 'fail' ? 'Copy failed' : label}
    </Button>
  )
}

function Picks({ title, picks, entities }: { title: string; picks: BriefPick[]; entities: Map<string, SlimEntity> }) {
  if (!picks.length) return null
  return (
    <section>
      <h3 className="mb-3 text-sm font-bold uppercase tracking-[0.12em] text-muted">{title}</h3>
      <ul className="grid gap-3 sm:grid-cols-2">
        {picks.map((p, i) => {
          const e = entities.get(p.entity_id)
          return (
            <li key={p.entity_id} className="flex gap-3 rounded-2xl border border-line bg-surface p-3">
              <EntityImage src={e?.image ?? null} name={p.name} className="h-16 w-16 shrink-0 rounded-xl" />
              <div className="min-w-0">
                <p className="font-bold leading-snug">{p.name}{title === 'Venue' && <span className="ml-2 text-xs font-medium text-muted">{i === 0 ? 'top pick' : 'backup'}</span>}</p>
                <p className="mt-0.5 text-sm text-ink-soft">{p.reason}</p>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

export default function BriefView({ plan }: { plan: PlanResponse }) {
  const b: Brief = plan.brief
  const entities = new Map<string, SlimEntity>()
  Object.values(plan.recommendations).forEach((recs) => recs?.forEach((r) => entities.set(r.entity.id, r.entity)))
  const md = briefToMarkdown(plan)

  return (
    <div className="space-y-8">
      <div className="rounded-3xl bg-night p-6 text-paper sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-accent">The concept</p>
            <h2 className="mt-2 text-lg font-semibold leading-snug sm:text-2xl sm:font-bold">{b.concept}</h2>
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
                <span className="text-ink-soft">{line}</span>
              </li>
            ))}
          </ol>
          <div className="mt-8 rounded-2xl border border-dashed border-line bg-surface p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-muted">Announcement for Discord / X</p>
            <p className="mt-2 font-medium">{b.promo_line}</p>
            <div className="mt-3"><CopyButton text={b.promo_line} label="Copy announcement" /></div>
          </div>
        </section>
        <div className="space-y-7">
          <Picks title="Music" picks={b.music} entities={entities} />
          <Picks title="Venue" picks={b.venue} entities={entities} />
          <Picks title="Sponsors" picks={b.sponsors} entities={entities} />
          <Picks title="Content" picks={b.content} entities={entities} />
        </div>
      </div>
      <p className="text-xs text-muted">
        Every pick above is a Qloo result{plan.dropped_picks > 0 ? `; ${plan.dropped_picks} AI-suggested pick(s) that Qloo did not return were removed` : ''}. Open a tab to see why each one was recommended.
      </p>
    </div>
  )
}
