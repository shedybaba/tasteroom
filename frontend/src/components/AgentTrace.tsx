import type { PlanResponse } from '../types'
import Icon from './Icon'

const TOOL_LABEL: Record<string, string> = {
  resolve_tastes: 'Match tastes to Qloo', resolve_city: 'Find the city', recommend: 'Ask Qloo for recommendations',
  find_venues: 'Scout venues', explain: 'Explain the picks', finish: 'Finish',
}

function argText(args: Record<string, unknown>) {
  const entries = Object.entries(args).filter(([, v]) => v !== null && v !== '' && v !== undefined)
  return entries.map(([k, v]) => `${k}: ${String(v)}`).join(' · ')
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
        <ol className="relative space-y-4 border-l-2 border-line pl-6">
          {plan.trace.map((t) => (
            <li key={t.step} className="relative">
              <span className={`absolute -left-[34px] grid h-5 w-5 place-items-center rounded-full text-white ${t.ok ? 'bg-ok' : 'bg-warn'}`}>
                <Icon name={t.ok ? 'check' : 'alert'} size={12} />
              </span>
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <code className="rounded bg-ink/6 px-1.5 py-0.5 text-sm font-semibold">{t.tool}</code>
                <span className="font-medium">{TOOL_LABEL[t.tool] ?? t.tool}</span>
                <span className="text-xs text-muted">{t.ms} ms</span>
              </div>
              {argText(t.args) && <p className="mt-0.5 text-sm text-muted">{argText(t.args)}</p>}
              <p className={`mt-0.5 text-sm ${t.ok ? 'text-ink-soft' : 'text-warn'}`}>{t.summary}</p>
            </li>
          ))}
        </ol>
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
                ? <span className="shrink-0 text-ok">→ {r.entity.name}</span>
                : <span className="shrink-0 text-warn">no match</span>}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  )
}
