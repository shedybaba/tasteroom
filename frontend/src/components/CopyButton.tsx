import { useState } from 'react'
import { copyText } from '../lib/format'
import Icon from './Icon'
import { Button } from './ui'

export default function CopyButton({ text, label, variant = 'ghost', className = '' }: { text: string; label: string; variant?: 'ghost' | 'dark'; className?: string }) {
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle')
  async function go() {
    setState((await copyText(text)) ? 'ok' : 'fail')
    setTimeout(() => setState('idle'), 2000)
  }
  return (
    <Button type="button" variant={variant} onClick={go} aria-live="polite" className={className}>
      <Icon name={state === 'ok' ? 'check' : 'copy'} size={16} />
      {state === 'ok' ? 'Copied' : state === 'fail' ? 'Copy failed: select and copy' : label}
    </Button>
  )
}
