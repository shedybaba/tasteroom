import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import AgentTrace from '../components/AgentTrace'
import BriefView from '../components/BriefView'
import CompareView from '../components/CompareView'
import EntityCard from '../components/EntityCard'
import ForEveryone from '../components/ForEveryone'
import Icon from '../components/Icon'
import LoadingSteps from '../components/LoadingSteps'
import RefineBox from '../components/RefineBox'
import ShareBar from '../components/ShareBar'
import VersionSwitcher from '../components/VersionSwitcher'
import WhatChanged from '../components/WhatChanged'
import { Button, ErrorState, ModeBadge, Spinner } from '../components/ui'
import { buildDisplayMap, DisplayContext } from '../lib/display'
import { DOMAIN_META, DOMAIN_ORDER } from '../lib/format'
import { REFINE_STEPS } from '../lib/refine'
import type { PlanResponse, VersionInfo } from '../types'

type TabKey = 'brief' | 'music' | 'venues' | 'brands' | 'content' | 'compare' | 'agent'

export default function Results({ example = false }: { example?: boolean }) {
  const { id = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const handed = (location.state as { plan?: PlanResponse } | null)?.plan
  const [loaded, setLoaded] = useState<{ id: string; plan?: PlanResponse; error?: ApiError } | null>(null)
  // Prefer the plan handed over by the Builder (instant), else whatever was fetched for this id.
  const plan = handed && handed.plan_id === id ? handed : loaded?.id === id ? (loaded.plan ?? null) : null
  const error = loaded?.id === id ? (loaded.error ?? null) : null

  useEffect(() => {
    if (plan) return
    let live = true
    const load = example ? api.examplePlan(id) : api.getPlan(id)
    load.then((p) => live && setLoaded({ id, plan: p })).catch((e: ApiError) => live && setLoaded({ id, error: e }))
    return () => { live = false }
  }, [id, example, plan])

  const [versions, setVersions] = useState<VersionInfo[]>([])
  const [refining, setRefining] = useState<string | null>(null)
  const [refineError, setRefineError] = useState<string | null>(null)
  const shared = !example && params.get('shared') === '1'   // read-only view opened from a Share link (presentation only: the API is public either way)
  const [balancing, setBalancing] = useState(false)
  const [balanceError, setBalanceError] = useState<string | null>(null)
  const planId = plan?.plan_id
  useEffect(() => {
    if (!planId) return
    let live = true
    api.versions(planId).then((v) => live && setVersions(v.versions)).catch(() => undefined)  // the switcher is optional
    return () => { live = false }
  }, [planId])

  const displayMap = useMemo(() => buildDisplayMap(plan?.resolved ?? []), [plan])
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  const tabs = useMemo(() => {
    if (!plan) return []
    const domains = DOMAIN_ORDER.filter((d) => (plan.recommendations[d]?.length ?? 0) > 0)
      .map((d) => ({ key: d as TabKey, label: DOMAIN_META[d].tab, count: plan.recommendations[d]!.length }))
    return [
      { key: 'brief' as TabKey, label: 'Brief' }, ...domains,
      { key: 'compare' as TabKey, label: 'Compare' }, { key: 'agent' as TabKey, label: 'How it worked' },
    ]
  }, [plan])

  if (error) {
    return <ErrorState title={error.status === 404 ? 'Plan not found' : 'Could not load this plan'} message={error.message}
      action={<Link to="/build"><Button>Plan a new event</Button></Link>} />
  }
  if (!plan) return <Spinner label="Loading your plan" />

  const requested = params.get('tab') as TabKey | null
  const active: TabKey = tabs.some((t) => t.key === requested) ? (requested as TabKey) : 'brief'
  async function runRefine(instruction: string) {
    setRefineError(null); setRefining(instruction)
    try {
      const child = await api.refine(plan!.plan_id, instruction)
      navigate(`/plan/${child.plan_id}`, { state: { plan: child } })
      setRefining(null)  // the router may reuse this component for the new route, so the "refining" screen must be cleared here
    } catch (e) {
      setRefineError((e as ApiError).message); setRefining(null)
    }
  }

  async function runBalance() {
    setBalanceError(null); setBalancing(true)
    try {
      const child = await api.balance(plan!.plan_id)
      navigate(`/plan/${child.plan_id}`, { state: { plan: child } })
    } catch (e) {
      setBalanceError((e as ApiError).message)
    }
    setBalancing(false)  // the router may reuse this component for the new route, so the busy state is cleared here
  }

  const select = (key: TabKey) => setParams({ ...(key === 'brief' ? {} : { tab: key }), ...(shared ? { shared: '1' } : {}) }, { replace: true })
  // ARIA tabs pattern: arrows/Home/End move between tabs; only the selected tab is in the Tab order.
  const onTabKey = (e: React.KeyboardEvent, i: number) => {
    const last = tabs.length - 1
    const next = e.key === 'ArrowRight' ? (i === last ? 0 : i + 1) : e.key === 'ArrowLeft' ? (i === 0 ? last : i - 1)
      : e.key === 'Home' ? 0 : e.key === 'End' ? last : -1
    if (next < 0) return
    e.preventDefault()
    select(tabs[next].key)
    tabRefs.current[next]?.focus()
  }
  const totalPicks = DOMAIN_ORDER.reduce((n, d) => n + (plan.recommendations[d]?.length ?? 0), 0)

  if (refining) {
    return <LoadingSteps title="Refining your plan" steps={REFINE_STEPS} intervalMs={5000}
      subtitle={`“${refining}”: usually 20 to 40 seconds. Only the parts it affects are re-queried.`} />
  }

  return (
    <DisplayContext.Provider value={displayMap}>
    <div className="mx-auto max-w-6xl px-4 py-8 sm:py-10">
      <header className="rise">
        <p className="text-sm font-medium text-muted">{plan.request.community_name} · {plan.request.city}</p>
        <h1 className="mt-1 text-3xl font-extrabold sm:text-5xl">{plan.brief.title}</h1>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <ModeBadge mode={plan.mode} />
          {shared && <span title="A read-only copy of a plan someone shared with you." className="inline-flex rounded-full bg-ok-soft px-2.5 py-1 text-xs font-semibold text-ok" data-testid="shared-badge">Shared plan</span>}
          {(plan.version ?? 1) > 1 && <span className="rounded-full bg-ink px-2.5 py-1 text-xs font-bold text-paper">v{plan.version}</span>}
          <span className="text-sm text-muted">{totalPicks} picks from Qloo · {plan.request.members.length} members</span>
          <span className="flex-1" />
          <Link to={example ? `/build?example=${id}` : '/build'}>
            <Button variant="ghost">{example ? 'Customize this example' : shared ? 'Plan your own event' : 'Plan another event'}</Button>
          </Link>
        </div>
        {plan.warnings.length > 0 && (
          <ul className="mt-4 space-y-1 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn" role="note">
            {plan.warnings.map((w) => <li key={w} className="flex gap-2"><Icon name="alert" size={16} className="mt-0.5 shrink-0" />{w}</li>)}
          </ul>
        )}
      </header>

      <div className="mt-4"><VersionSwitcher versions={versions} current={plan.plan_id} shared={shared} /></div>
      {plan.refinement && <WhatChanged refinement={plan.refinement} />}
      <ShareBar plan={plan} isExample={example} shareOnly={shared} />
      {!shared && <RefineBox busy={refining !== null} error={refineError} onRun={runRefine} />}

      <div role="tablist" aria-label="Plan sections" className="no-scrollbar -mx-4 mt-8 flex gap-1 overflow-x-auto border-b border-line px-4">
        {tabs.map((t, i) => (
          <button key={t.key} ref={(el) => { tabRefs.current[i] = el }} role="tab" id={`tab-${t.key}`}
            aria-selected={active === t.key} aria-controls={`panel-${t.key}`} tabIndex={active === t.key ? 0 : -1}
            onClick={() => select(t.key)} onKeyDown={(e) => onTabKey(e, i)}
            // Selected = bold ink text + accent underline. Keyboard focus = an ink outline box (never an underline),
            // so the two can't be confused; mouse clicks don't show it (focus-visible only).
            className={`-mb-px shrink-0 whitespace-nowrap rounded-t-md border-b-2 px-4 py-3 text-sm transition-colors focus-visible:bg-ink/5 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink ${active === t.key ? 'border-accent font-bold text-ink' : 'border-transparent font-semibold text-muted hover:text-ink'}`}>
            {t.label}{'count' in t && <span className="ml-1.5 rounded-full bg-ink/8 px-1.5 py-0.5 text-[11px]">{t.count}</span>}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${active}`} aria-labelledby={`tab-${active}`} className="pt-8">
        {active === 'brief' && <BriefView plan={plan} balancing={balancing} balanceError={balanceError} onBalance={shared ? undefined : runBalance} />}
        {active === 'compare' && <CompareView plan={plan} isExample={example} />}
        {active === 'agent' && <AgentTrace plan={plan} />}
        {(active === 'music' || active === 'venues' || active === 'brands' || active === 'content') && (
          <>
            <p className="mb-6 max-w-2xl text-ink-soft">{DOMAIN_META[active].blurb}</p>
            {(active === 'music' || active === 'content') && (plan.personal?.length || plan.personal_skipped?.length) ? (
              <h2 className="mb-3 text-sm font-bold uppercase tracking-[0.12em] text-accent">Crowd-pleasers</h2>
            ) : null}
            <div className="grid items-start gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {plan.recommendations[active]!.map((r, i) => <EntityCard key={r.entity.id} rec={r} rank={i + 1} />)}
            </div>
            {(active === 'music' || active === 'content') && <ForEveryone plan={plan} domain={active} />}
          </>
        )}
      </div>
    </div>
    </DisplayContext.Provider>
  )
}
