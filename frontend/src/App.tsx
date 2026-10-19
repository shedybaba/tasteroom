import { useEffect, useState } from 'react'

type Health = { ok: boolean; qloo: 'live' | 'mock'; llm: 'live' | 'mock' }

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setError(true))
  }, [])

  return (
    <main className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-4xl font-bold tracking-tight">TasteRoom</h1>
      <p className="mt-3 text-lg text-neutral-600">
        Stop guessing what your community wants. Plan events from real taste data.
      </p>
      <p className="mt-8 text-sm text-neutral-500">
        {error && 'Backend unreachable.'}
        {health && `Qloo: ${health.qloo} · LLM: ${health.llm}`}
      </p>
    </main>
  )
}
