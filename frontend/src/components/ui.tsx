import type { ReactNode } from 'react'
import type { PlanMode } from '../types'
import Icon from './Icon'

export function ModeBadge({ mode }: { mode: PlanMode }) {
  const m: Record<PlanMode, { label: string; tip: string; cls: string }> = {
    agent: { label: 'AI agent', tip: 'An AI agent chose the domains and filters for this event.', cls: 'bg-accent-soft text-accent' },
    pipeline: { label: 'Standard pipeline', tip: 'The fixed-order fallback pipeline built this plan.', cls: 'bg-ink/8 text-ink-soft' },
    precomputed: { label: 'Example', tip: 'A saved example run, so it opens instantly.', cls: 'bg-ok-soft text-ok' },
    mock: { label: 'Demo data', tip: 'Built from saved sample data, not live Qloo calls.', cls: 'bg-warn-soft text-warn' },
  }
  const { label, tip, cls } = m[mode]
  return <span title={tip} className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${cls}`}>{label}</span>
}

export function Chip({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'dark' }) {
  const tones = { neutral: 'bg-ink/6 text-ink-soft', accent: 'bg-accent-soft text-accent', dark: 'bg-paper/12 text-paper' }
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>
}

export function Button({ variant = 'primary', className = '', ...props }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'dark' }) {
  const v = {
    primary: 'bg-accent text-white hover:bg-[#d13d22] disabled:bg-accent/40',
    dark: 'bg-ink text-paper hover:bg-ink-soft disabled:bg-ink/40',
    ghost: 'border border-line bg-surface text-ink hover:border-ink/30 disabled:opacity-50',
  }[variant]
  return (
    <button {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed ${v} ${className}`} />
  )
}

export function ErrorState({ title = 'Something went wrong', message, action }: { title?: string; message: string; action?: ReactNode }) {
  return (
    <div role="alert" className="mx-auto my-16 max-w-md rounded-2xl border border-line bg-surface p-6 text-center shadow-card">
      <div className="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-full bg-warn-soft text-warn"><Icon name="alert" /></div>
      <h2 className="text-lg font-bold">{title}</h2>
      <p className="mt-1 text-sm text-muted">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" className="grid place-items-center py-24 text-muted">
      <span className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-accent" />
      <span className="mt-3 text-sm">{label}…</span>
    </div>
  )
}

export function SectionTitle({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return (
    <div className="mb-6">
      {eyebrow && <p className="mb-1 text-xs font-bold uppercase tracking-[0.14em] text-accent">{eyebrow}</p>}
      <h2 className="text-2xl font-extrabold sm:text-3xl">{title}</h2>
      {children && <p className="mt-2 max-w-2xl text-muted">{children}</p>}
    </div>
  )
}
