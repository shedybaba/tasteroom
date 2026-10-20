import { Link } from 'react-router-dom'
import { versionLabel } from '../lib/refine'
import type { VersionInfo } from '../types'

/** v1 · v2 · v3 … links between the versions of one plan. */
export default function VersionSwitcher({ versions, current, shared = false }: { versions: VersionInfo[]; current: string; shared?: boolean }) {
  if (versions.length < 2) return null
  return (
    <nav aria-label="Plan versions" className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs font-semibold text-muted">Versions</span>
      {versions.map((v) => {
        const active = v.plan_id === current
        return (
          <Link key={v.plan_id} to={v.example ? `/example/${v.plan_id}` : `/plan/${v.plan_id}${shared ? '?shared=1' : ''}`} aria-current={active ? 'page' : undefined}
            title={v.instruction ? `“${v.instruction}”` : 'The first plan'}
            className={`rounded-full border px-3 py-1 text-sm font-semibold ${active ? 'border-ink bg-ink text-paper' : 'border-line bg-surface hover:border-ink/40'}`}>
            {versionLabel(v)}
          </Link>
        )
      })}
    </nav>
  )
}
