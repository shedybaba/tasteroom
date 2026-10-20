import { useMemberName } from '../lib/display'

/** "Personal pick · Priya": marks a lineup pick that was chosen for a member, visible without reading the text. */
export default function PersonalBadge({ members }: { members: string[] }) {
  const name = useMemberName()
  if (!members.length) return null
  return (
    <span data-testid="personal-badge" className="inline-flex items-center rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-bold text-accent">
      Personal pick · {members.map(name).join(' & ')}
    </span>
  )
}
