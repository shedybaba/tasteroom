import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import CopyButton from '../components/CopyButton'
import EntityImage from '../components/EntityImage'
import Icon from '../components/Icon'
import LoadingSteps from '../components/LoadingSteps'
import QrCode from '../components/QrCode'
import { Button, ErrorState, Spinner } from '../components/ui'
import { capNote, inviteMessage, joinPath, POLL_MS, responseCountText, saveRoom } from '../lib/rooms'
import type { RoomResponse, RoomResponses } from '../types'

function Chips({ r }: { r: RoomResponse }) {
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5">
      {r.tastes.map((t, i) => (
        <li key={i} className={`inline-flex max-w-full items-center gap-1.5 rounded-full border py-0.5 pr-2.5 text-xs font-medium ${t.name ? 'border-ok/30 bg-ok-soft pl-0.5' : 'border-line bg-paper pl-2.5'}`}
          title={t.name ? `Matched in Qloo: ${t.name}` : 'Typed text: matched when the plan is built'}>
          {t.name && <EntityImage src={t.image ?? null} name={t.name} eager className="h-5 w-5 shrink-0 rounded-full" />}
          <span className="truncate">{t.name ?? t.text}</span>
        </li>
      ))}
    </ul>
  )
}

/** The organizer's control center: share the link, watch responses arrive, build the plan. */
export default function OrganizerRoom() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const token = params.get('t') ?? ''
  const navigate = useNavigate()
  const [data, setData] = useState<RoomResponses | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [stale, setStale] = useState(false)
  const [fresh, setFresh] = useState<Set<number>>(new Set())
  const [announce, setAnnounce] = useState('')
  const [building, setBuilding] = useState(false)
  const [buildError, setBuildError] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const seen = useRef<Set<number> | null>(null)
  const stop = useRef(false)

  // Poll every 10 s while the tab is visible (and immediately when it becomes visible again).
  useEffect(() => {
    if (!token) return
    const ctrl = new AbortController()
    stop.current = false
    const tick = () => {
      if (document.hidden || stop.current) return
      api.roomResponses(slug, token, ctrl.signal).then((d) => {
        setData(d); setStale(false); setError(null)
        const ids = new Set(d.responses.map((r) => r.id))
        if (seen.current) {
          const arrived = d.responses.filter((r) => !seen.current!.has(r.id))
          if (arrived.length) {
            const ids = arrived.map((r) => r.id)
            setFresh((f) => new Set([...f, ...ids]))
            setAnnounce(`${arrived.map((r) => r.name).join(', ')} just joined`)
            setTimeout(() => setFresh((f) => new Set([...f].filter((id) => !ids.includes(id)))), 12_000)  // the "New" badge fades
          }
        } else if (!d.room.demo) {
          saveRoom({ slug, token, name: d.room.community_name, city: d.room.city })  // so the organizer can find it again
        }
        seen.current = ids
      }).catch((e: unknown) => {
        if (ctrl.signal.aborted) return
        if (e instanceof ApiError && e.status === 404) { stop.current = true; setError(e) } else setStale(true)  // transient: keep what we have
      })
    }
    tick()
    const timer = setInterval(tick, POLL_MS)
    const onVisible = () => { if (!document.hidden) tick() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { ctrl.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', onVisible) }
  }, [slug, token])

  const joinUrl = `${window.location.origin}${joinPath(slug)}`
  const message = useMemo(() => data ? inviteMessage({ community: data.room.community_name, goal: data.room.event_goal, city: data.room.city, url: joinUrl }) : '', [data, joinUrl])

  async function build() {
    setBuildError(null); setBuilding(true)
    try {
      const plan = await api.roomPlan(slug, token)
      navigate(`/plan/${plan.plan_id}`, { state: { plan } })
    } catch (e) {
      setBuildError((e as ApiError).message); setBuilding(false)
    }
  }
  async function remove(id: number) {
    setConfirmId(null)
    try {
      await api.removeResponse(slug, token, id)
      setData((d) => d && { ...d, responses: d.responses.filter((r) => r.id !== id), room: { ...d.room, response_count: d.room.response_count - 1 } })
    } catch (e) { setBuildError((e as ApiError).message) }
  }

  if (!token) {
    return <ErrorState title="This link is missing its host key" message="Open the host link you saved when you created the room (it ends in ?t=…). Guests use the join link instead."
      action={<Link to="/build"><Button>Create a new room</Button></Link>} />
  }
  if (error) {
    return <ErrorState title="We could not open this room" message={error.message}
      action={<Link to="/build"><Button>Create a new room</Button></Link>} />
  }
  if (!data) return <Spinner label="Opening your room" />
  if (building) return <LoadingSteps />

  const { room, responses, plan } = data
  const n = responses.length
  const canBuild = n >= plan.min
  const note = capNote(n, plan.will_use, plan.left_out)

  return (
    <div className="mx-auto max-w-5xl px-4 pb-32 pt-8">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-accent">{room.demo ? 'Demo room' : 'Your room'}</p>
      <h1 className="mt-1 text-3xl font-extrabold sm:text-4xl">{room.community_name}</h1>
      <p className="mt-2 text-ink-soft">{room.event_goal} · {room.city}</p>
      {room.demo && (
        <p className="mt-4 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn" role="note">
          This is a live demo room with 8 pre-filled people. Scan the QR code or open the join link on your phone, add yourself,
          and watch the response appear here within 10 seconds. Visitor responses are cleared after 12 hours.
        </p>
      )}
      {buildError && <p role="alert" className="mt-4 flex gap-2 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn"><Icon name="alert" size={18} className="mt-0.5 shrink-0" />{buildError}</p>}

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[1.15fr_1fr]">
        <section aria-labelledby="resp-h" className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="resp-h" className="text-xl font-extrabold" data-testid="response-count">{responseCountText(n)}</h2>
            <span className="inline-flex items-center gap-1.5 text-xs text-muted" role="status">
              <span className={`h-2 w-2 rounded-full ${stale ? 'bg-warn' : 'animate-pulse bg-ok'}`} aria-hidden="true" />
              {stale ? 'Reconnecting…' : 'Updating live'}
            </span>
          </div>
          <p className="sr-only" aria-live="polite">{announce}</p>
          {n === 0 ? (
            <p className="mt-4 rounded-xl border border-dashed border-line p-5 text-sm text-muted">
              Share the link and responses will appear here as people submit them. You need at least {plan.min} to build a plan.
            </p>
          ) : (
            <ul className="mt-4 space-y-3">
              {responses.map((r) => (
                <li key={r.id} className={`rounded-2xl border p-3 ${fresh.has(r.id) ? 'border-accent/50 bg-accent-soft/40' : 'border-line'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-bold">{r.name}{fresh.has(r.id) && <span className="ml-2 rounded-full bg-accent px-2 py-0.5 text-[10px] font-bold uppercase text-white">New</span>}</p>
                    {confirmId === r.id ? (
                      <span className="flex items-center gap-2 text-xs">
                        <button type="button" onClick={() => remove(r.id)} className="font-semibold text-warn underline underline-offset-2">Remove {r.name}</button>
                        <button type="button" onClick={() => setConfirmId(null)} className="text-muted underline underline-offset-2">Cancel</button>
                      </span>
                    ) : (
                      <button type="button" onClick={() => setConfirmId(r.id)} aria-label={`Remove ${r.name}'s response`}
                        className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-ink/8 hover:text-ink"><Icon name="x" size={14} /></button>
                    )}
                  </div>
                  <Chips r={r} />
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="space-y-6">
          <section aria-labelledby="inv-h" className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <h2 id="inv-h" className="text-xl font-extrabold">Invite everyone</h2>
            <p className="mt-1 text-sm text-muted">Anyone with this link can add their tastes. No login, about 30 seconds on a phone.</p>
            <div className="mt-4 flex flex-col items-center gap-4 sm:flex-row sm:items-start">
              <QrCode value={joinUrl} />
              <div className="w-full min-w-0 flex-1">
                <label className="text-xs font-semibold text-muted" htmlFor="join-url">Join link</label>
                <input id="join-url" readOnly value={joinUrl} onFocus={(e) => e.currentTarget.select()}
                  className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm" />
                <div className="mt-2 flex flex-wrap gap-2">
                  <CopyButton text={joinUrl} label="Copy link" />
                  <a href={joinPath(slug)} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center rounded-full border border-line px-4 py-2.5 text-sm font-semibold hover:border-ink/30">Open join page</a>
                </div>
              </div>
            </div>
            <label className="mt-5 block text-xs font-semibold text-muted" htmlFor="invite-msg">Message for WhatsApp, Discord or the family chat</label>
            <textarea id="invite-msg" readOnly rows={5} value={message} onFocus={(e) => e.currentTarget.select()}
              className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm" />
            <div className="mt-2"><CopyButton text={message} label="Copy message" /></div>
          </section>

          {!room.demo && (
            <section className="rounded-3xl border border-dashed border-line p-5">
              <h2 className="text-base font-extrabold">Save your host link</h2>
              <p className="mt-1 text-sm text-muted">This page is the only way back to your responses, and the key in the link is shown once. Bookmark it or copy it somewhere safe. Do not share it: it lets people remove responses and build plans.</p>
              <div className="mt-3"><CopyButton text={window.location.href} label="Copy host link" /></div>
            </section>
          )}
        </div>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-paper/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3">
          <Button type="button" onClick={build} disabled={!canBuild}>
            {canBuild ? `Build the plan from ${plan.will_use} responses` : 'Build the plan'} <Icon name="arrow" size={16} />
          </Button>
          <p className="min-w-0 flex-1 basis-full text-sm text-muted sm:basis-0" aria-live="polite">
            {!canBuild ? `You need at least ${plan.min} responses (${n} so far).` : note ?? `Ready: all ${n} responses will be used.`}
          </p>
        </div>
      </div>
    </div>
  )
}
