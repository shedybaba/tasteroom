import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import Icon from '../components/Icon'
import MemberCard from '../components/MemberCard'
import { Button, ErrorState, Spinner } from '../components/ui'
import { useIdeas } from '../lib/ideas'
import { clearJoined, joinedAs, markJoined } from '../lib/rooms'
import { toRequestMember, type UIMember } from '../lib/tastes'
import type { RoomInfo } from '../types'

/** What a guest sees when the host shares the link: no login, one card, about 30 seconds. */
export default function JoinRoom() {
  const { slug = '' } = useParams()
  const [room, setRoom] = useState<RoomInfo | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [member, setMember] = useState<UIMember>({ name: '', tastes: [] })
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [nameError, setNameError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(() => joinedAs(slug))
  const ideas = useIdeas(room?.city ?? '')

  useEffect(() => {
    let live = true
    api.roomInfo(slug).then((r) => live && setRoom(r)).catch((e: ApiError) => live && setLoadError(e))
    return () => { live = false }
  }, [slug])

  const name = member.name.trim()
  const count = member.tastes.filter((t) => t.text.trim()).length
  const ready = name.length > 0 && count > 0

  async function submit() {
    setError(null); setNameError(null); setSending(true)
    try {
      await api.joinRoom(slug, toRequestMember(member, name))
      markJoined(slug, name)
      setDone(name)
      window.scrollTo({ top: 0, behavior: 'instant' })
    } catch (e) {
      const err = e as ApiError
      // A name problem belongs next to the name field; anything else goes in the banner.
      if (err.status === 409 && /name/i.test(err.message)) setNameError(err.message)
      else if (err.status === 422 && /name|nickname/i.test(err.message)) setNameError(err.message)
      else setError(err.message)
    } finally { setSending(false) }
  }

  if (loadError) {
    return <ErrorState title={loadError.status === 404 ? 'We could not find this room' : 'Could not open this room'} message={loadError.message}
      action={<Link to="/"><Button>Go to TasteRoom</Button></Link>} />
  }
  if (!room) return <Spinner label="Opening the room" />

  if (done) {
    return (
      <div className="mx-auto max-w-md px-4 py-14 text-center">
        <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-ok-soft text-ok"><Icon name="check" size={28} /></div>
        <h1 className="text-3xl font-extrabold">You&rsquo;re in{done ? `, ${done}` : ''}.</h1>
        <p className="mt-3 text-lg text-ink-soft">The host will build the plan.</p>
        <p className="mt-2 text-sm text-muted">{room.community_name} · {room.event_goal}</p>
        <div className="mt-8 flex flex-col items-center gap-3">
          <button type="button" onClick={() => { clearJoined(slug); setDone(null); setMember({ name: '', tastes: [] }) }}
            className="text-sm font-semibold text-ink underline underline-offset-4">Add another person from this phone</button>
          <Link to="/" className="text-sm text-muted underline-offset-4 hover:underline">Planning an event of your own? Try TasteRoom</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-xl px-4 pb-32 pt-8">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-accent">You&rsquo;re invited</p>
      <h1 className="mt-1 text-3xl font-extrabold leading-tight sm:text-4xl">{room.community_name} wants to know what you like</h1>
      <p className="mt-3 text-ink-soft">{room.event_goal} · {room.city}</p>
      <p className="mt-2 text-sm text-muted">
        Takes about 30 seconds, no sign-up. Every prompt is optional: tap an idea or start typing. The host sees your first name and your picks.
      </p>

      {room.demo && (
        <p className="mt-4 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn" role="note">
          This is the demo room. Go ahead and add yourself: the host page shows it live.
        </p>
      )}
      {error && <p role="alert" className="mt-4 flex gap-2 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn"><Icon name="alert" size={18} className="mt-0.5 shrink-0" />{error}</p>}

      <div className="mt-6">
        <MemberCard variant="join" index={0} member={member} city={room.city} ideas={ideas} check={() => undefined}
          canRemove={false} onChange={(m) => { setMember(m); setNameError(null) }} onRemove={() => undefined} nameError={nameError} />
      </div>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-paper/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-xl items-center gap-3">
          <Button type="button" onClick={submit} disabled={!ready || sending} className="flex-1 py-3 text-base sm:flex-none">
            {sending ? 'Sending…' : 'Send my picks'} <Icon name="arrow" size={16} />
          </Button>
          <p className="min-w-0 flex-1 text-xs text-muted" aria-live="polite">
            {!name ? 'Add your first name or a nickname' : count === 0 ? 'Add at least one thing you like' : `${count} added. You can send now.`}
          </p>
        </div>
      </div>
    </div>
  )
}
