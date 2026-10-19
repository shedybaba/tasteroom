import { useState } from 'react'
import { initials } from '../lib/format'

/** Qloo image with a graceful fallback (gradient + initials) for missing or broken URLs. */
export default function EntityImage({ src, name, className = '' }: { src: string | null; name: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) {
    return (
      <div aria-hidden="true" className={`grid place-items-center bg-gradient-to-br from-ink-soft to-ink font-display text-2xl font-extrabold text-paper/80 ${className}`}>
        {initials(name)}
      </div>
    )
  }
  return <img src={src} alt={name} loading="lazy" onError={() => setFailed(true)} className={`object-cover ${className}`} />
}
