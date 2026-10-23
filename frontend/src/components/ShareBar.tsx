import { useEffect, useRef, useState } from 'react'
import { pollText, sharePath } from '../lib/share'
import type { PostService } from '../lib/share'
import type { PlanResponse } from '../types'
import AnnouncementPost, { SERVICES } from './AnnouncementPost'
import CopyButton from './CopyButton'
import Icon from './Icon'

const ORDER: PostService[] = ['discord', 'slack']

/** Share the plan, copy a venue poll, post to Discord or Slack. `shareOnly` (the read-only shared view) keeps just the link.
 *  One "Post to" button opens a small menu with the two services; choosing one opens its webhook panel, and the same button
 *  reopens the menu to switch. */
export default function ShareBar({ plan, isExample, shareOnly = false }: { plan: PlanResponse; isExample: boolean; shareOnly?: boolean }) {
  const [service, setService] = useState<PostService | null>(null)
  const [menu, setMenu] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const items = useRef<(HTMLButtonElement | null)[]>([])
  const link = `${window.location.origin}${sharePath(plan.plan_id, isExample)}`
  const poll = pollText(plan)

  // Close the menu on a click anywhere else.
  useEffect(() => {
    if (!menu) return
    const away = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setMenu(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [menu])
  useEffect(() => { if (menu) items.current[Math.max(service ? ORDER.indexOf(service) : 0, 0)]?.focus() }, [menu, service])

  const choose = (s: PostService) => { setService(s); setMenu(false); button.current?.focus() }
  const onMenuKey = (e: React.KeyboardEvent) => {
    const at = items.current.findIndex((el) => el === document.activeElement)
    if (e.key === 'Escape') { e.preventDefault(); setMenu(false); button.current?.focus() }
    else if (e.key === 'ArrowDown') { e.preventDefault(); items.current[(at + 1) % ORDER.length]?.focus() }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items.current[(at - 1 + ORDER.length) % ORDER.length]?.focus() }
    else if (e.key === 'Tab') setMenu(false)
  }

  return (
    <section aria-label="Share this plan" className="mt-6" data-testid="share-bar">
      <div className="flex flex-wrap items-center gap-3">
        <CopyButton text={link} label="Share" />
        {!shareOnly && poll && <CopyButton text={poll} label="Copy a poll for the group" />}
        {!shareOnly && (
          <div ref={wrap} className="relative">
            {/* a plain button (same look as the ghost Button) so the menu can take focus back to it */}
            <button ref={button} type="button" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((o) => !o)} data-testid="post-menu-button"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-line bg-surface px-5 py-2.5 text-sm font-semibold text-ink transition-colors hover:border-ink/30">
              <Icon name="arrow" size={16} />{service ? `Post to ${SERVICES[service].name}` : 'Post to…'}<Icon name="down" size={14} />
            </button>
            {menu && (
              <div role="menu" aria-label="Post to" onKeyDown={onMenuKey}
                className="absolute left-0 top-full z-20 mt-1 min-w-44 rounded-xl border border-line bg-surface p-1 shadow-card">
                {ORDER.map((s, i) => (
                  <button key={s} ref={(el) => { items.current[i] = el }} type="button" role="menuitemradio" aria-checked={service === s} onClick={() => choose(s)}
                    data-testid={`${SERVICES[s].prefix}-toggle`}
                    className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm font-semibold hover:bg-ink/6 focus-visible:bg-ink/6">
                    {SERVICES[s].name}{service === s && <Icon name="check" size={14} />}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <p className="mt-2 text-xs text-muted">
        {isExample ? 'Anyone with the link can open this example.' : 'Anyone with the link can view this plan (read-only), including everyone’s first names and tastes.'}
      </p>
      {!shareOnly && service && <AnnouncementPost key={service} planId={plan.plan_id} service={service} onClose={() => setService(null)} />}
    </section>
  )
}
