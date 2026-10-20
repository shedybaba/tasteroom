import type { PlanResponse } from '../types'
import { shownName } from '../lib/display'
import { BALANCE_INSTRUCTION } from '../lib/coverage'
import Icon from './Icon'

const TOOL_LABEL: Record<string, string> = {
  resolve_tastes: 'Match tastes to Qloo', resolve_city: 'Find the city', recommend: 'Ask Qloo for recommendations',
  find_venues: 'Scout venues', explain: 'Explain the picks', finish: 'Finish',
  find_tags: 'Look up Qloo tags', list_neighbourhoods: 'List neighbourhoods', balance_lineup: 'Balance the lineup', personal_picks: 'Find each member\u2019s personal pick',
}

function StepList({ steps }: { steps: PlanResponse['trace'] }) {
  return (
    <ol className="relative space-y-4 border-l-2 border-line pl-6">
      {steps.map((t) => (
        <li key={t.step} className="relative">
          <span className={`absolute -left-[34px] grid h-5 w-5 place-items-center rounded-full text-white ${t.ok ? 'bg-ok' : 'bg-warn'}`}>
            <Icon name={t.ok ? 'check' : 'alert'} size={12} />
          </span>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <code className="rounded bg-ink/6 px-1.5 py-0.5 text-sm font-semibold">{t.tool}</code>
            <span className="font-medium">{TOOL_LABEL[t.tool] ?? t.tool}</span>
            <span className="text-xs text-muted">{t.ms} ms</span>
          </div>
          <ArgChips args={t.args} inferred={t.inferred ?? []} refined={t.refined ?? []} />
          <p className={`mt-0.5 text-sm ${t.ok ? 'text-ink-soft' : 'text-warn'}`}>{t.summary}</p>
        </li>
      ))}
    </ol>
  )
}

/** The arguments actually applied. Ones taken from the event goal (not set by the organizer) are labelled. */
function ArgChips({ args, inferred, refined }: { args: Record<string, unknown>; inferred: string[]; refined: string[] }) {
  const entries = Object.entries(args).filter(([, v]) => v !== null && v !== '' && v !== undefined && v !== false)
  if (!entries.length) return null
  return (
    <p className="mt-1 flex flex-wrap gap-1.5 text-sm text-muted">
      {entries.map(([k, v]) => (
        <span key={k} className="inline-flex items-center gap-1.5 rounded-md bg-ink/5 px-1.5 py-0.5">
          <span>{k}: <span className="font-medium text-ink-soft">{v === true ? 'on' : String(v)}</span></span>
          {inferred.includes(k) && <span className="rounded bg-accent-soft px-1 text-[11px] font-semibold text-accent">inferred from your goal</span>}
          {refined.includes(k) && <span className="rounded bg-accent px-1 text-[11px] font-semibold text-white">from your refinement</span>}
        </span>
      ))}
    </p>
  )
}

export default function AgentTrace({ plan }: { plan: PlanResponse }) {
  const total = plan.trace.reduce((s, t) => s + t.ms, 0)
  const matched = plan.resolved.filter((r) => r.entity).length
  const intro: Record<string, string> = {
    agent: 'An AI agent read the event goal and chose which tools to call, and with which filters. Every step below is a real call.',
    pipeline: 'The AI agent was unavailable or incomplete, so a fixed pipeline ran the same tools in order. Results are equally grounded in Qloo.',
    precomputed: 'This example was saved from a real run. The steps below are what was executed.',
    mock: 'Built from saved sample data (no live Qloo calls).',
  }
  return (
    <div className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
      <section>
        <p className="mb-5 max-w-2xl text-ink-soft">{intro[plan.mode]}</p>
        {plan.refinement ? (
          <>
            <h3 className="mb-3 text-sm font-bold uppercase tracking-[0.12em] text-muted">Original run</h3>
            <StepList steps={plan.trace.slice(0, plan.refinement.trace_start)} />
            <h3 className="mb-1 mt-8 text-sm font-bold uppercase tracking-[0.12em] text-accent" data-testid="refinement-heading">Refinement</h3>
            {plan.refinement.instruction === BALANCE_INSTRUCTION
              ? <p className="mb-3 text-sm text-ink-soft">You asked to balance the lineup. No new Qloo search ran: the swaps were taken from the results already on this plan, then the brief was rewritten.</p>
              : <p className="mb-3 text-sm text-ink-soft">You asked: &ldquo;{plan.refinement.instruction}&rdquo;. The agent re-ran only what that affects; every other part of the plan was kept.</p>}
            <StepList steps={plan.trace.slice(plan.refinement.trace_start)} />
          </>
        ) : <StepList steps={plan.trace} />}
        <p className="mt-6 text-sm text-muted">{plan.trace.length} steps · {(total / 1000).toFixed(1)} s of tool time</p>
      </section>

      <aside className="h-fit rounded-2xl border border-line bg-surface p-5">
        <h3 className="font-bold">How tastes were matched</h3>
        <p className="mt-1 text-sm text-muted">{matched} of {plan.resolved.length} tastes matched to Qloo entities{plan.locality ? ` · city: ${plan.locality.name}` : ''}</p>
        <ul className="mt-4 max-h-96 space-y-1.5 overflow-auto pr-1 text-sm">
          {plan.resolved.map((r, i) => (
            <li key={i} className="flex items-baseline justify-between gap-3">
              <span><span className="font-medium">{r.member}</span> <span className="text-muted">· {r.input}</span></span>
              {r.entity
                ? <span className="shrink-0 text-ok" title={`Qloo entity: ${r.entity.name}`}>→ {shownName(r.input, r.entity.name)}</span>
                : <span className="shrink-0 text-warn">no match</span>}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  )
}
