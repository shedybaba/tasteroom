import { useState } from 'react'
import type { Recommendation } from '../types'
import { fitSummary, safeUrl, typeLabel } from '../lib/format'
import EntityImage from './EntityImage'
import Icon from './Icon'
import WhyPanel from './WhyPanel'

export default function EntityCard({ rec, rank }: { rec: Recommendation; rank: number }) {
  const [open, setOpen] = useState(false)
  const e = rec.entity
  const site = safeUrl(e.website)
  const panelId = `why-${e.id}`
  return (
    <article className="flex flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
      <div className="relative">
        <EntityImage src={e.image} name={e.name} className="aspect-[4/3] w-full" />
        <span className="absolute left-3 top-3 grid h-7 w-7 place-items-center rounded-full bg-ink/80 text-xs font-bold text-paper backdrop-blur">{rank}</span>
        <span className="absolute right-3 top-3 rounded-full bg-paper/90 px-2.5 py-1 text-xs font-semibold text-ink backdrop-blur">{typeLabel(e.type)}</span>
      </div>
      <div className="flex flex-1 flex-col p-4">
        <h3 className="text-lg font-bold leading-snug">{e.name}</h3>
        {e.address && (
          <p className="mt-1 flex items-start gap-1.5 text-sm text-muted"><Icon name="pin" size={15} className="mt-0.5 shrink-0" /><span className="line-clamp-2">{e.address}</span></p>
        )}
        {e.description && <p className="mt-2 line-clamp-3 text-sm text-ink-soft">{e.description}</p>}
        <p className="mt-3 text-sm font-semibold text-accent">{fitSummary(rec)}</p>
        <div className="mt-auto flex items-center justify-between pt-3">
          <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((o) => !o)}
            className="inline-flex items-center gap-1 text-sm font-semibold text-ink underline-offset-4 hover:underline">
            {open ? 'Hide why' : 'Why this pick'}
            <Icon name="down" size={16} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>
          {site && <a href={site} target="_blank" rel="noopener noreferrer" className="text-sm text-muted underline-offset-4 hover:underline">Website</a>}
        </div>
        {open && <div id={panelId}><WhyPanel rec={rec} /></div>}
      </div>
    </article>
  )
}
