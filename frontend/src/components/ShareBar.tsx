import { useState } from 'react'
import { pollText, sharePath } from '../lib/share'
import type { PlanResponse } from '../types'
import CopyButton from './CopyButton'
import DiscordPost from './DiscordPost'
import Icon from './Icon'
import { Button } from './ui'

/** Share the plan, copy a venue poll, post to Discord. `shareOnly` (the read-only shared view) keeps just the link. */
export default function ShareBar({ plan, isExample, shareOnly = false }: { plan: PlanResponse; isExample: boolean; shareOnly?: boolean }) {
  const [discord, setDiscord] = useState(false)
  const link = `${window.location.origin}${sharePath(plan.plan_id, isExample)}`
  const poll = pollText(plan)
  return (
    <section aria-label="Share this plan" className="mt-6" data-testid="share-bar">
      <div className="flex flex-wrap items-center gap-3">
        <CopyButton text={link} label="Share" />
        {!shareOnly && poll && <CopyButton text={poll} label="Copy a poll for my members" />}
        {!shareOnly && (
          <Button type="button" variant="ghost" aria-expanded={discord} onClick={() => setDiscord((o) => !o)} data-testid="discord-toggle">
            <Icon name="arrow" size={16} />Post to Discord
          </Button>
        )}
      </div>
      <p className="mt-2 text-xs text-muted">
        {isExample ? 'Anyone with the link can open this example.' : 'Anyone with the link can view this plan (read-only), including members’ first names and tastes.'}
      </p>
      {!shareOnly && discord && <DiscordPost planId={plan.plan_id} onClose={() => setDiscord(false)} />}
    </section>
  )
}
