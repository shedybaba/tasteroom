import { useState } from 'react'
import { initials } from '../lib/format'

/** Qloo image with a graceful fallback (gradient + initials) for missing or broken URLs. */
export default function EntityImage({ src, name, className = '', eager = false }: { src: string | null; name: string; className?: string; eager?: boolean }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) {
    return (
      <div aria-hidden="true" className={`grid place-items-center bg-gradient-to-br from-ink-soft to-ink font-display text-2xl font-extrabold text-paper/80 ${className}`}>
        {initials(name)}
      </div>
    )
  }
  // Neutral tile while loading, so a slow image never leaves a hole. `eager` for images that are visible at once.
  return <img src={src} alt={name} loading={eager ? 'eager' : 'lazy'} decoding="async" onError={() => setFailed(true)} className={`bg-ink/8 object-cover ${className}`} />
}
