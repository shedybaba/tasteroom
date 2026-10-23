import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import Icon from '../components/Icon'
import LoadingSteps from '../components/LoadingSteps'
import MemberCard from '../components/MemberCard'
import { Button, SectionTitle } from '../components/ui'
import { useIdeas } from '../lib/ideas'
import { loadRooms, organizerPath, saveRoom } from '../lib/rooms'
import { MAX_MEMBERS, MIN_MEMBERS, parsePasted, toRequestMember, toUIMember } from '../lib/tastes'
import type { CheckState, UIMember, UITaste } from '../lib/tastes'
import type { Member, PlanOptions, PlanRequest, SlimEntity } from '../types'

const GOAL_CHIPS = ['Night out with friends', 'Family dinner', 'Team offsite', 'Chill meetup', 'Launch party', 'Watch party']
const DAYS = ['', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

const blankMember = (): UIMember => ({ name: '', tastes: [] })
const DEFAULT_OPTIONS: PlanOptions = { hidden_gems: false, price_level_max: null, day: null, venue_kind: null }

const checkKey = (mi: number, t: UITaste) => `${mi}|${t.kind}|${t.text.trim().toLowerCase()}`

export default function Builder() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [community, setCommunity] = useState('')
  const [city, setCity] = useState('')
  const [goal, setGoal] = useState(() => params.get('goal')?.slice(0, 200) ?? '')
  const [members, setMembers] = useState<UIMember[]>([blankMember(), blankMember(), blankMember()])
  const [options, setOptions] = useState<PlanOptions>(DEFAULT_OPTIONS)
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const [checks, setChecks] = useState<Map<string, SlimEntity | null>>(new Map())
  const [locality, setLocality] = useState<SlimEntity | null | undefined>(undefined)
  const [checking, setChecking] = useState(false)
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const recentRooms = useMemo(() => loadRooms(), [])

  // "Customize this example" prefill
  const exampleId = params.get('example')
  useEffect(() => {
    if (!exampleId) return
    api.examples().then((all) => {
      const ex = all.find((e) => e.id === exampleId)
      if (!ex) return
      setCommunity(ex.request.community_name); setCity(ex.request.city); setGoal(ex.request.event_goal)
      setMembers(ex.request.members.map(toUIMember)); setOptions(ex.request.options)
    }).catch(() => undefined)
  }, [exampleId])

  const ideas = useIdeas(city)
  const named = useMemo(() => members.map((m, i) => ({ ...m, name: m.name.trim() || `Member ${i + 1}` })), [members])
  const filled = named.filter((m) => m.tastes.length > 0)
  const problems = [
    !community.trim() && 'Give your group a name',
    !city.trim() && 'Enter the city for your get-together',
    !goal.trim() && 'Describe the event you want',
    filled.length < MIN_MEMBERS && `Add tastes for at least ${MIN_MEMBERS} people (${filled.length} so far)`,
  ].filter(Boolean) as string[]

  // A taste picked from autocomplete is matched already (no "Check tastes" needed); typed text waits for a check.
  const stateFor = (mi: number, ti: number): CheckState => {
    const t = members[mi].tastes[ti]
    if (t.pick) return { name: t.pick.name, image: t.pick.image }
    const key = checkKey(mi, t)
    return checks.has(key) ? checks.get(key) : undefined
  }
  const unchecked = members.reduce((n, m, mi) => n + m.tastes.filter((t, ti) => !t.pick && stateFor(mi, ti) === undefined).length, 0)
  const checked = filled.length > 0 && unchecked === 0
  const misses = members.flatMap((m, mi) => m.tastes.filter((_, ti) => stateFor(mi, ti) === null)).length
  const checkLabel = unchecked > 0 ? 'Check tastes' : !locality && city.trim() ? 'Check city' : 'Re-check tastes'

  function setMember(i: number, m: UIMember) { setMembers((all) => all.map((x, j) => (j === i ? m : x))) }

  async function checkTastes() {
    setError(null); setChecking(true)
    try {
      // Only typed tastes need a server check; picked ones carry their Qloo entity. Flatten in the same order the
      // server returns results, remembering each key.
      const order: string[] = []
      const send: Member[] = []
      members.forEach((m, mi) => {
        const typed = m.tastes.filter((t) => !t.pick && t.text.trim())
        if (!typed.length) return
        send.push({ name: named[mi].name, tastes: typed.map(({ text, kind }) => ({ text, kind })) })
        typed.forEach((t) => order.push(checkKey(mi, t)))
      })
      const res = await api.resolve(send, city)
      const next = new Map<string, SlimEntity | null>()
      res.resolved.forEach((r, i) => next.set(order[i], r.entity))
      setChecks(next); setLocality(res.locality)
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setChecking(false) }
  }

  async function createRoom() {
    setError(null); setCreating(true)
    try {
      const room = await api.createRoom({ community_name: community.trim(), city: city.trim(), event_goal: goal.trim() })
      saveRoom({ slug: room.slug, token: room.organizer_token, name: community.trim(), city: city.trim() })
      navigate(room.organizer_path)
    } catch (e) {
      setError((e as ApiError).message); setCreating(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  async function build() {
    setError(null); setBuilding(true)
    const req: PlanRequest = {
      community_name: community.trim(), city: city.trim(), event_goal: goal.trim(),
      members: filled.map((m) => toRequestMember(m, m.name)), options,
    }
    try {
      const plan = await api.plan(req)
      navigate(`/plan/${plan.plan_id}`, { state: { plan } })
    } catch (e) {
      setError((e as ApiError).message); setBuilding(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  if (building) return <LoadingSteps />

  const input = 'w-full rounded-xl border border-line bg-surface px-4 py-3 placeholder:text-muted focus:border-ink/40'
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <SectionTitle eyebrow="Plan an event" title="Who’s coming?">
        Add what 3 to 15 people like. Every prompt is optional: tap an idea or start typing, and suggestions come straight from Qloo. The more varied, the better the picks.
      </SectionTitle>

      {error && <p role="alert" className="mb-6 flex gap-2 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn"><Icon name="alert" size={18} className="mt-0.5 shrink-0" />{error}</p>}

      <div className="grid gap-4 md:grid-cols-2">
        <label className="block"><span className="mb-1 block text-sm font-semibold">Group name</span>
          <input className={input} value={community} maxLength={80} onChange={(e) => setCommunity(e.target.value)} placeholder="Ada’s birthday crew" /></label>
        <label className="block"><span className="mb-1 block text-sm font-semibold">City for the event</span>
          <input className={input} value={city} maxLength={80} onChange={(e) => { setCity(e.target.value); setLocality(undefined) }} placeholder="Lagos" />
          {locality && <span className="mt-1 block text-xs text-ok">Matched on the Qloo map: {locality.name}</span>}
          {locality === null && <span className="mt-1 block text-xs text-warn">City not found; venues will fall back to a name search.</span>}
        </label>
      </div>
      <div className="mt-4">
        <label className="block"><span className="mb-1 block text-sm font-semibold">What are you planning?</span>
          <input className={input} value={goal} maxLength={200} onChange={(e) => setGoal(e.target.value)} placeholder="Saturday dinner and live music for 12 friends" /></label>
        <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Quick picks">
          {GOAL_CHIPS.map((c) => (
            <button key={c} type="button" onClick={() => setGoal(c)}
              className="rounded-full border border-line bg-surface px-3 py-1 text-sm font-medium hover:border-ink/40">{c}</button>
          ))}
        </div>
      </div>

      <section aria-labelledby="collect-h" className="mt-8 rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex-1 basis-64">
            <h2 id="collect-h" className="text-base font-extrabold">Rather not type everyone&rsquo;s tastes?</h2>
            <p className="mt-0.5 text-sm text-muted">Share one link in WhatsApp, Discord or the family chat. Everyone adds their own picks on their phones and you build the plan from their answers.</p>
          </div>
          <Button type="button" variant="dark" onClick={createRoom} disabled={creating || !community.trim() || !city.trim() || !goal.trim()}>
            <Icon name="users" size={16} /> {creating ? 'Creating…' : 'Collect tastes from everyone'}
          </Button>
        </div>
        {(!community.trim() || !city.trim() || !goal.trim()) && <p className="mt-2 text-xs text-muted">Fill in the group name, city and what you are planning above first.</p>}
        {recentRooms.length > 0 && (
          <p className="mt-3 border-t border-line pt-3 text-xs text-muted">
            Your recent rooms:{' '}
            {recentRooms.map((r, i) => (
              <span key={r.slug}>{i > 0 && ' · '}<Link to={organizerPath(r.slug, r.token)} className="font-semibold text-ink underline underline-offset-2">{r.name}</Link></span>
            ))}
          </p>
        )}
      </section>

      <div className="mb-3 mt-8 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-xl font-extrabold">People <span className="text-base font-medium text-muted">({members.length}/{MAX_MEMBERS})</span></h2>
        <Button type="button" variant="ghost" onClick={() => setPasteOpen((o) => !o)} aria-expanded={pasteOpen}><Icon name="list" size={16} /> Paste a list</Button>
      </div>

      {pasteOpen && (
        <div className="mb-4 rounded-2xl border border-line bg-surface p-4">
          <label className="block text-sm font-semibold" htmlFor="paste">One person per line: <code className="font-normal text-muted">Name: taste, taste, taste</code></label>
          <textarea id="paste" rows={5} value={pasteText} onChange={(e) => setPasteText(e.target.value)}
            placeholder={'Ada: Burna Boy, Tems, Nike\nTunde: Wizkid, Money Heist, Guaranty Trust Bank'}
            className="mt-2 w-full rounded-xl border border-line bg-paper px-3 py-2 text-sm focus:border-ink/40" />
          <div className="mt-2 flex gap-2">
            <Button type="button" variant="dark" disabled={!parsePasted(pasteText).length}
              onClick={() => { setMembers(parsePasted(pasteText).map(toUIMember)); setChecks(new Map()); setPasteText(''); setPasteOpen(false) }}>Use this list</Button>
            <Button type="button" variant="ghost" onClick={() => setPasteOpen(false)}>Cancel</Button>
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {members.map((m, i) => (
          <MemberCard key={i} index={i} member={m} city={city} ideas={ideas} check={(ti) => stateFor(i, ti)}
            canRemove={members.length > MIN_MEMBERS} onChange={(nm) => setMember(i, nm)}
            onRemove={() => setMembers((all) => all.filter((_, j) => j !== i))} />
        ))}
        {members.length < MAX_MEMBERS && (
          <button type="button" onClick={() => setMembers((all) => [...all, blankMember()])}
            className="grid min-h-40 place-items-center rounded-2xl border-2 border-dashed border-line text-muted transition-colors hover:border-ink/30 hover:text-ink">
            <span className="flex items-center gap-2 font-semibold"><Icon name="plus" size={18} /> Add person</span>
          </button>
        )}
      </div>

      <details className="mt-8 rounded-2xl border border-line bg-surface p-4">
        <summary className="cursor-pointer font-semibold">Options <span className="font-normal text-muted">(hidden gems, price, day, venue type)</span></summary>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" checked={options.hidden_gems} onChange={(e) => setOptions({ ...options, hidden_gems: e.target.checked })} className="mt-1 h-4 w-4 accent-[var(--color-accent)]" />
            <span><span className="font-semibold">Hidden gems</span><br /><span className="text-muted">Favour less mainstream picks</span></span>
          </label>
          <label className="block text-sm"><span className="mb-1 block font-semibold">Max venue price</span>
            <select value={options.price_level_max ?? ''} onChange={(e) => setOptions({ ...options, price_level_max: e.target.value ? Number(e.target.value) : null })} className="w-full rounded-lg border border-line bg-surface px-2 py-2">
              <option value="">Any</option><option value="1">$</option><option value="2">$$</option><option value="3">$$$</option><option value="4">$$$$</option>
            </select></label>
          <label className="block text-sm"><span className="mb-1 block font-semibold">Event day</span>
            <select value={options.day ?? ''} onChange={(e) => setOptions({ ...options, day: e.target.value || null })} className="w-full rounded-lg border border-line bg-surface px-2 py-2 capitalize">
              {DAYS.map((d) => <option key={d} value={d}>{d || 'Any'}</option>)}
            </select></label>
          <label className="block text-sm"><span className="mb-1 block font-semibold">Venue type</span>
            <input value={options.venue_kind ?? ''} maxLength={40} onChange={(e) => setOptions({ ...options, venue_kind: e.target.value || null })} placeholder="bar, cafe, park…" className="w-full rounded-lg border border-line bg-surface px-3 py-2" /></label>
        </div>
      </details>

      <div className="sticky bottom-0 -mx-4 mt-8 border-t border-line bg-paper/95 px-4 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
          <Button type="button" variant="ghost" onClick={checkTastes} disabled={checking || (filled.length === 0 && !city.trim())}>
            {checking ? 'Checking…' : checkLabel}
          </Button>
          <Button type="button" onClick={build} disabled={problems.length > 0}>Build event plan <Icon name="arrow" size={16} /></Button>
          <p className="basis-full text-sm text-muted sm:min-w-0 sm:flex-1 sm:basis-0" aria-live="polite">
            {problems.length > 0 ? problems[0]
              : checked ? (misses ? `${misses} taste${misses > 1 ? 's' : ''} didn’t match; fix or remove ${misses > 1 ? 'them' : 'it'} for best results.` : 'All tastes matched.')
              : 'Tip: check tastes first to catch misspellings.'}
          </p>
        </div>
      </div>
    </div>
  )
}
