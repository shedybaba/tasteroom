import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import EntityImage from '../components/EntityImage'
import Icon from '../components/Icon'
import type { IconName } from '../components/Icon'
import { Chip, SectionTitle } from '../components/ui'
import type { ExampleSummary, SlimEntity } from '../types'

const STEPS: { icon: IconName; title: string; text: string }[] = [
  { icon: 'users', title: 'Tell us what members like', text: 'Add 3 to 15 members with a few artists, shows, brands or places each. Paste a list if you already have one.' },
  { icon: 'bot', title: 'An agent queries Qloo', text: 'It matches every taste to Qloo’s taste graph, then decides which of music, venues, sponsors and content your event needs.' },
  { icon: 'list', title: 'Get a brief you can run', text: 'A run of show with real picks, each explained by the members and shared tags behind it.' },
]

function Collage({ items }: { items: SlimEntity[] }) {
  const tilt = ['-rotate-3', 'rotate-2', 'rotate-3', '-rotate-2', 'rotate-1', '-rotate-1']
  return (
    <div className="grid grid-cols-3 gap-3" aria-hidden="true">
      {items.slice(0, 6).map((e, i) => (
        <div key={e.id} className={`${tilt[i]} ${i % 2 ? 'translate-y-4' : ''} overflow-hidden rounded-2xl border border-paper/15 shadow-xl`}>
          <EntityImage src={e.image} name={e.name} className="aspect-square w-full" />
        </div>
      ))}
    </div>
  )
}

export default function Landing() {
  const [examples, setExamples] = useState<ExampleSummary[] | null>(null)
  const [collage, setCollage] = useState<SlimEntity[]>([])
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    api.examples().then(setExamples).catch(() => setFailed(true))
    api.examplePlan('lagos-creators').then((p) => {
      // Artist photos only: Qloo's venue photos are inconsistent in quality.
      setCollage((p.recommendations.music ?? []).map((r) => r.entity).filter((e) => e.image).slice(0, 6))
    }).catch(() => undefined)
  }, [])

  return (
    <>
      <section className="overflow-hidden bg-night text-paper">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-14 sm:py-20 lg:grid-cols-[1.1fr_1fr]">
          <div className="rise">
            <p className="mb-4 inline-flex items-center gap-2 rounded-full bg-paper/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-paper/80">
              <Icon name="spark" size={14} /> Built on Qloo taste data
            </p>
            <h1 className="text-4xl font-extrabold leading-[1.05] sm:text-6xl">Stop guessing what your community wants.</h1>
            <p className="mt-5 max-w-xl text-lg text-paper/75">
              Plan events from real taste data. Tell TasteRoom what your members like and an AI agent builds the event brief:
              artists, venues, sponsors and shows, <em className="not-italic text-paper">each one explained</em>.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/build" className="inline-flex items-center gap-2 rounded-full bg-accent px-6 py-3 font-semibold text-white transition-colors hover:bg-[#ff6247]">
                Plan for my community <Icon name="arrow" size={18} />
              </Link>
              <a href="#examples" className="inline-flex items-center rounded-full border border-paper/25 px-6 py-3 font-semibold text-paper transition-colors hover:bg-paper/10">See an example</a>
            </div>
          </div>
          <div className="hidden lg:block">{collage.length >= 4 && <Collage items={collage} />}</div>
        </div>
        {collage.length >= 4 && <div className="mx-auto max-w-6xl px-4 pb-10 lg:hidden"><Collage items={collage.slice(0, 3)} /></div>}
      </section>

      <section id="examples" className="mx-auto max-w-6xl scroll-mt-16 px-4 py-14">
        <SectionTitle eyebrow="Try it instantly" title="Start from an example community">
          Each one opens a complete, saved plan in under a second. Open the Compare tab to see what Qloo adds over a plain AI answer.
        </SectionTitle>
        {failed && <p className="rounded-xl bg-warn-soft p-4 text-warn" role="alert">Examples could not be loaded. You can still build your own plan.</p>}
        <div className="grid gap-5 md:grid-cols-3">
          {!examples && !failed && [0, 1, 2].map((i) => <div key={i} className="h-72 animate-pulse rounded-3xl bg-ink/6" />)}
          {examples?.map((ex) => (
            <Link key={ex.id} to={`/example/${ex.id}`}
              className="group flex flex-col rounded-3xl border border-line bg-surface p-5 shadow-card transition-transform hover:-translate-y-1">
              <div className="flex items-center justify-between">
                <Chip tone="accent">{ex.city}</Chip>
                <span className="text-xs text-muted">{ex.members.length} members</span>
              </div>
              <h3 className="mt-4 text-xl font-extrabold">{ex.name}</h3>
              <p className="mt-1 text-sm text-ink-soft">{ex.tagline}</p>
              <p className="mt-3 text-sm font-medium">{ex.goal}</p>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {[...new Set(ex.members.slice(0, 4).flatMap((m) => m.tastes.slice(0, 2)))].slice(0, 6).map((t) => <Chip key={t}>{t}</Chip>)}
              </div>
              <span className="mt-auto inline-flex items-center gap-1.5 pt-5 text-sm font-semibold text-accent">
                Open the plan <Icon name="arrow" size={16} className="transition-transform group-hover:translate-x-1" />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="border-y border-line bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-14">
          <SectionTitle eyebrow="How it works" title="From member tastes to a run of show" />
          <ol className="grid gap-6 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className="flex gap-4">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent"><Icon name={s.icon} size={22} /></span>
                <div>
                  <p className="text-xs font-bold text-muted">Step {i + 1}</p>
                  <h3 className="text-lg font-bold">{s.title}</h3>
                  <p className="mt-1 text-sm text-ink-soft">{s.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14">
        <div className="grid items-center gap-6 rounded-3xl bg-night p-8 text-paper md:grid-cols-[1.3fr_1fr]">
          <div>
            <h2 className="text-2xl font-extrabold sm:text-3xl">An AI alone would just guess.</h2>
            <p className="mt-2 text-paper/75">
              TasteRoom only recommends what Qloo returns for your community, in your city, and shows who each pick suits.
              Anything the AI suggests that Qloo doesn’t back is removed.
            </p>
          </div>
          <div className="flex md:justify-end">
            <Link to="/build" className="inline-flex items-center gap-2 rounded-full bg-accent px-6 py-3 font-semibold text-white hover:bg-[#ff6247]">
              Plan an event <Icon name="arrow" size={18} />
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
