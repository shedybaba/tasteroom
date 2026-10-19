import { Link, NavLink, Outlet, ScrollRestoration } from 'react-router-dom'

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="relative inline-block h-6 w-9" aria-hidden="true">
        <span className="absolute left-0 top-0 h-6 w-6 rounded-full bg-accent" />
        <span className={`absolute left-3.5 top-0 h-6 w-6 rounded-full ${light ? 'bg-paper/90' : 'bg-ink/85'} mix-blend-multiply`} />
      </span>
      <span className="font-display text-xl font-extrabold tracking-tight">TasteRoom</span>
    </span>
  )
}

const navCls = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${isActive ? 'bg-ink text-paper' : 'text-ink-soft hover:bg-ink/5'}`

export default function Layout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" aria-label="TasteRoom home"><Logo /></Link>
          <nav className="flex items-center gap-1" aria-label="Main">
            <NavLink to="/" end className={navCls}>Examples</NavLink>
            <NavLink to="/build" className={navCls}>Plan an event</NavLink>
          </nav>
        </div>
      </header>
      <main className="flex-1"><Outlet /></main>
      <footer className="border-t border-line bg-paper">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>Every recommendation comes from <strong className="font-semibold text-ink">Qloo</strong> taste data. The AI only organises it.</p>
          <p>Built for the Qloo Agentic Hackathon · MIT licensed</p>
        </div>
      </footer>
      <ScrollRestoration />
    </div>
  )
}
