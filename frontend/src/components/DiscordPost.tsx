import { useId, useState } from 'react'
import { api, ApiError } from '../api'
import { isWebhookUrl } from '../lib/share'
import type { DiscordPayload } from '../types'
import Icon from './Icon'
import { Button } from './ui'

type Step = 'enter' | 'loading' | 'preview' | 'posting' | 'done'

/** What will be posted, drawn like the Discord message it becomes. The text is the server's own payload, so this is exactly
 *  what gets sent. */
function Preview({ payload }: { payload: DiscordPayload }) {
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

/** Post the announcement to a Discord channel. Three deliberate steps (paste, read exactly what will be sent, confirm).
 *  The webhook URL only ever lives in this component's state: no storage, no URL, cleared as soon as the post succeeds. */
export default function DiscordPost({ planId, onClose }: { planId: string; onClose: () => void }) {
  const uid = useId()
  const [url, setUrl] = useState('')
  const [step, setStep] = useState<Step>('enter')
  const [payload, setPayload] = useState<DiscordPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const valid = isWebhookUrl(url)

  async function preview() {
    setError(null); setStep('loading')
    try { setPayload((await api.announcement(planId)).payload); setStep('preview') }
    catch (e) { setError((e as ApiError).message); setStep('enter') }
  }
  async function confirm() {
    setError(null); setStep('posting')
    try { await api.postToDiscord(planId, url.trim()); setUrl(''); setPayload(null); setStep('done') }
    catch (e) { setError((e as ApiError).message); setStep('preview') }
  }

  return (
    <section aria-labelledby={`${uid}-h`} className="mt-4 rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5" data-testid="discord-panel">
      <div className="flex items-start justify-between gap-3">
        <h2 id={`${uid}-h`} className="text-base font-extrabold">Post the announcement to Discord</h2>
        <button type="button" onClick={onClose} aria-label="Close the Discord panel" className="rounded-md p-1 text-muted hover:text-ink"><Icon name="x" size={18} /></button>
      </div>

      {step === 'done' ? (
        <p role="status" className="mt-3 flex items-start gap-2 text-sm text-ok" data-testid="discord-done">
          <Icon name="check" size={18} className="mt-0.5 shrink-0" />Posted. The webhook URL was used once and has been cleared from this page; nothing was saved.
        </p>
      ) : step === 'preview' || step === 'posting' ? (
        <>
          <p className="mt-1 text-sm text-muted">This is exactly what will be posted. Nothing is sent until you confirm. The message cannot ping anyone.</p>
          <div className="mt-3">{payload && <Preview payload={payload} />}</div>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button onClick={confirm} disabled={step === 'posting'} data-testid="discord-confirm">{step === 'posting' ? 'Posting…' : 'Confirm and post to Discord'}</Button>
            <Button variant="ghost" onClick={() => setStep('enter')} disabled={step === 'posting'}>Back</Button>
          </div>
        </>
      ) : (
        <>
          <p className="mt-1 text-sm text-muted">
            Paste a webhook URL for the channel (Discord: channel settings &rarr; Integrations &rarr; Webhooks &rarr; Copy Webhook URL).
            It is used once to post this message and is never stored.
          </p>
          <label htmlFor={`${uid}-url`} className="mt-3 block text-sm font-semibold">Discord webhook URL</label>
          {/* type=password: the URL is a secret, so it is not shown on screen, saved by the browser or kept in history */}
          <input id={`${uid}-url`} type="password" autoComplete="off" spellCheck={false} maxLength={300} value={url} placeholder="https://discord.com/api/webhooks/…"
            onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && valid && step === 'enter') void preview() }}
            aria-invalid={url.length > 0 && !valid} aria-describedby={`${uid}-hint`}
            className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 text-base placeholder:text-muted focus:border-ink/40 sm:text-sm" />
          <p id={`${uid}-hint`} className="mt-1 text-xs text-muted">{url.length > 0 && !valid ? 'That does not look like a Discord webhook URL (it starts with https://discord.com/api/webhooks/).' : 'You will see the message before anything is sent.'}</p>
          <div className="mt-3"><Button onClick={preview} disabled={!valid || step === 'loading'} data-testid="discord-preview-button">{step === 'loading' ? 'Preparing…' : 'Preview the post'}</Button></div>
        </>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-warn" data-testid="discord-error">{error}</p>}
    </section>
  )
}
