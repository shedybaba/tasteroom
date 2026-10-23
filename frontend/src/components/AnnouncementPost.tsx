import { useId, useState } from 'react'
import type { ReactNode } from 'react'
import { api, ApiError } from '../api'
import { isSlackWebhookUrl, isWebhookUrl } from '../lib/share'
import type { PostService } from '../lib/share'
import type { DiscordPayload, SlackPayload } from '../types'
import Icon from './Icon'
import { Button } from './ui'

type Step = 'enter' | 'loading' | 'preview' | 'posting' | 'done'
type Payload = DiscordPayload | SlackPayload

interface ServiceInfo {
  name: string
  prefix: string          // test ids: discord-panel, slack-panel, ...
  placeholder: string
  startsWith: string
  howTo: ReactNode
  valid: (url: string) => boolean
}

export const SERVICES: Record<PostService, ServiceInfo> = {
  discord: {
    name: 'Discord', prefix: 'discord', placeholder: 'https://discord.com/api/webhooks/…', startsWith: 'https://discord.com/api/webhooks/',
    howTo: <>Paste a webhook URL for the channel (Discord: channel settings &rarr; Integrations &rarr; Webhooks &rarr; Copy Webhook URL).</>,
    valid: isWebhookUrl,
  },
  slack: {
    name: 'Slack', prefix: 'slack', placeholder: 'https://hooks.slack.com/services/…', startsWith: 'https://hooks.slack.com/services/',
    howTo: <>Paste an incoming-webhook URL for the channel (Slack: create an Incoming Webhook at api.slack.com/messaging/webhooks and copy its URL).</>,
    valid: isSlackWebhookUrl,
  },
}

/** Slack's mini-markup as the preview shows it: *bold* and <url|label> links, with &amp; &lt; &gt; turned back into characters. */
function slackText(text: string): ReactNode[] {
  const unescape = (t: string) => t.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
  return text.split(/(\*[^*]+\*|<[^|>]+\|[^>]+>)/g).filter(Boolean).map((part, i) => {
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) return <strong key={i}>{unescape(part.slice(1, -1))}</strong>
    const link = /^<([^|>]+)\|([^>]+)>$/.exec(part)
    if (link) return <span key={i} className="font-semibold text-[#8ac4ff] underline underline-offset-2">{unescape(link[2])}</span>
    return <span key={i}>{unescape(part)}</span>
  })
}

/** What will be posted, drawn like the Discord message it becomes. The text is the server's own payload, so this is exactly
 *  what gets sent. */
function DiscordPreview({ payload }: { payload: DiscordPayload }) {
  const e = payload.embeds[0]
  return (
    <figure className="rounded-xl bg-night p-4 text-paper" aria-label="The Discord message that will be posted" data-testid="discord-preview">
      <p className="text-xs font-semibold text-paper/60">{payload.username} · BOT</p>
      <p className="mt-1 whitespace-pre-wrap text-sm" data-testid="discord-preview-content">{payload.content}</p>
      {e && (
        <div className="mt-2 rounded-lg border-l-4 border-accent bg-white/6 p-3 text-sm">
          <p className="font-bold">{e.title}</p>
          <p className="mt-0.5 text-paper/80">{e.description}</p>
          {e.fields.map((f) => (
            <div key={f.name} className="mt-2"><p className="text-xs font-bold text-paper/70">{f.name}</p><p className="whitespace-pre-wrap">{f.value}</p></div>
          ))}
          {e.url && <p className="mt-2 break-all text-xs text-paper/60">Link in the title: {e.url}</p>}
          <p className="mt-2 text-xs text-paper/50">{e.footer.text}</p>
        </div>
      )}
    </figure>
  )
}

/** The Slack message, drawn block by block (header, text, two columns, link, footer) from the server's own payload. */
function SlackPreview({ payload }: { payload: SlackPayload }) {
  return (
    <figure className="rounded-xl bg-night p-4 text-sm text-paper" aria-label="The Slack message that will be posted" data-testid="slack-preview">
      <p className="text-xs font-semibold text-paper/60">TasteRoom · APP</p>
      <div className="mt-2 space-y-2 border-l-4 border-accent pl-3">
        {payload.blocks.map((b, i) => {
          if (b.type === 'header') return <p key={i} className="text-base font-extrabold">{b.text.text}</p>
          if (b.type === 'context') return <p key={i} className="text-xs text-paper/50">{b.elements.map((el) => el.text).join(' ')}</p>
          return (
            <div key={i}>
              {b.text && <p className="whitespace-pre-wrap" data-testid={i === 1 ? 'slack-preview-content' : undefined}>{slackText(b.text.text)}</p>}
              {b.fields && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {b.fields.map((f, j) => <p key={j} className="whitespace-pre-wrap">{slackText(f.text)}</p>)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </figure>
  )
}

/** Post the announcement to a Discord or Slack channel. Three deliberate steps (paste, read exactly what will be sent, confirm).
 *  The webhook URL only ever lives in this component's state: no storage, no URL, cleared as soon as the post succeeds. The parent
 *  keys this component by service, so switching service starts over with an empty URL. */
export default function AnnouncementPost({ planId, service, onClose }: { planId: string; service: PostService; onClose: () => void }) {
  const info = SERVICES[service]
  const t = info.prefix
  const uid = useId()
  const [url, setUrl] = useState('')
  const [step, setStep] = useState<Step>('enter')
  const [payload, setPayload] = useState<Payload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const valid = info.valid(url)

  async function preview() {
    setError(null); setStep('loading')
    try {
      setPayload(service === 'slack' ? (await api.slackAnnouncement(planId)).payload : (await api.announcement(planId)).payload)
      setStep('preview')
    } catch (e) { setError((e as ApiError).message); setStep('enter') }
  }
  async function confirm() {
    setError(null); setStep('posting')
    try {
      await (service === 'slack' ? api.postToSlack(planId, url.trim()) : api.postToDiscord(planId, url.trim()))
      setUrl(''); setPayload(null); setStep('done')
    } catch (e) { setError((e as ApiError).message); setStep('preview') }
  }

  return (
    <section aria-labelledby={`${uid}-h`} className="mt-4 rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5" data-testid={`${t}-panel`}>
      <div className="flex items-start justify-between gap-3">
        <h2 id={`${uid}-h`} className="text-base font-extrabold">Post the announcement to {info.name}</h2>
        <button type="button" onClick={onClose} aria-label={`Close the ${info.name} panel`} className="rounded-md p-1 text-muted hover:text-ink"><Icon name="x" size={18} /></button>
      </div>

      {step === 'done' ? (
        <p role="status" className="mt-3 flex items-start gap-2 text-sm text-ok" data-testid={`${t}-done`}>
          <Icon name="check" size={18} className="mt-0.5 shrink-0" />Posted. The webhook URL was used once and has been cleared from this page; nothing was saved.
        </p>
      ) : step === 'preview' || step === 'posting' ? (
        <>
          <p className="mt-1 text-sm text-muted">This is exactly what will be posted. Nothing is sent until you confirm. The message cannot ping anyone.</p>
          <div className="mt-3">
            {payload && (service === 'slack' ? <SlackPreview payload={payload as SlackPayload} /> : <DiscordPreview payload={payload as DiscordPayload} />)}
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button onClick={confirm} disabled={step === 'posting'} data-testid={`${t}-confirm`}>{step === 'posting' ? 'Posting…' : `Confirm and post to ${info.name}`}</Button>
            <Button variant="ghost" onClick={() => setStep('enter')} disabled={step === 'posting'}>Back</Button>
          </div>
        </>
      ) : (
        <>
          <p className="mt-1 text-sm text-muted">{info.howTo} It is used once to post this message and is never stored.</p>
          <label htmlFor={`${uid}-url`} className="mt-3 block text-sm font-semibold">{info.name} webhook URL</label>
          {/* type=password: the URL is a secret, so it is not shown on screen, saved by the browser or kept in history */}
          <input id={`${uid}-url`} type="password" autoComplete="off" spellCheck={false} maxLength={300} value={url} placeholder={info.placeholder}
            onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && valid && step === 'enter') void preview() }}
            aria-invalid={url.length > 0 && !valid} aria-describedby={`${uid}-hint`}
            className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 text-base placeholder:text-muted focus:border-ink/40 sm:text-sm" />
          <p id={`${uid}-hint`} className="mt-1 text-xs text-muted">{url.length > 0 && !valid ? `That does not look like a ${info.name} webhook URL (it starts with ${info.startsWith}).` : 'You will see the message before anything is sent.'}</p>
          <div className="mt-3"><Button onClick={preview} disabled={!valid || step === 'loading'} data-testid={`${t}-preview-button`}>{step === 'loading' ? 'Preparing…' : 'Preview the post'}</Button></div>
        </>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-warn" data-testid={`${t}-error`}>{error}</p>}
    </section>
  )
}
