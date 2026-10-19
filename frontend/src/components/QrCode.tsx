import { useEffect, useState } from 'react'

/** QR code generated in the browser (the `qrcode` package is loaded only when this is shown). */
export default function QrCode({ value, size = 176 }: { value: string; size?: number }) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let live = true
    import('qrcode')
      .then((m) => m.toDataURL(value, { width: size * 2, margin: 1, errorCorrectionLevel: 'M', color: { dark: '#1f1630', light: '#ffffff' } }))
      .then((url) => live && setSrc(url))
      .catch(() => live && setFailed(true))
    return () => { live = false }
  }, [value, size])
  if (failed) return <p className="text-xs text-muted">The QR code could not be drawn. Use the link instead.</p>
  return src
    ? <img src={src} width={size} height={size} alt="QR code that opens the join page" className="rounded-xl border border-line bg-white p-2" />
    : <div style={{ width: size, height: size }} className="animate-pulse rounded-xl bg-ink/8" role="status" aria-label="Drawing QR code" />
}
