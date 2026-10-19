import { useEffect, useState } from 'react'

const STEPS = [
  'Matching every member’s tastes to Qloo entities',
  'Finding your city on the taste map',
  'Letting the agent decide what this event needs',
  'Asking Qloo for artists, venues, sponsors and shows',
  'Working out why each pick fits',
  'Writing your event brief',
]

/** Staged progress for the non-streaming plan call (~10-60 s). Real work happens server-side; the
 *  copy mirrors the backend's actual stages, and the last step stays up until the response lands. */
export default function LoadingSteps() {
  const [active, setActive] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setActive((a) => Math.min(a + 1, STEPS.length - 1)), 5000)
    return () => clearInterval(t)
  }, [])
  return (
    <div role="status" aria-live="polite" className="mx-auto my-16 max-w-md rounded-3xl border border-line bg-surface p-6 shadow-card sm:p-8">
      <h2 className="text-xl font-extrabold">Building your event plan</h2>
      <p className="mt-1 text-sm text-muted">Usually 30 to 60 seconds (up to 90 for big communities): it is making real calls to Qloo.</p>
      <ol className="mt-6 space-y-3">
        {STEPS.map((s, i) => (
          <li key={s} className={`flex items-center gap-3 text-sm transition-opacity ${i > active ? 'opacity-35' : ''}`}>
            <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-bold ${i < active ? 'bg-ok text-white' : i === active ? 'bg-accent text-white' : 'bg-ink/10 text-muted'}`}>
              {i < active ? '✓' : i + 1}
            </span>
            <span className={i === active ? 'font-semibold' : ''}>{s}{i === active && <span className="ml-1 inline-block animate-pulse">…</span>}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
