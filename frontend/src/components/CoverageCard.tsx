import { coverageHeadline } from '../lib/coverage'
import { useMemberName } from '../lib/display'
import type { Coverage } from '../types'
import { Button } from './ui'

/** One line: do all members have a pick made for them (a personal pick, or one that stands out), plus a button that moves the
 *  personal picks into the main lineup (existing results only). The cards above show who got what, and the Compare tab keeps the
 *  strict "stands out" count apart from personal picks, so nothing is blurred here. */
export default function CoverageCard({ coverage, busy, error, onBalance }: {
  coverage: Coverage; busy: boolean; error: string | null; onBalance?: () => void   // no onBalance = read-only (shared view)
}) {
  const name = useMemberName()
  if (coverage.total < 2) return null
  const swaps = coverage.balance.length
  return (
    <section aria-label="Coverage" className="-mt-2 rounded-2xl border border-line bg-surface px-4 py-3 sm:px-5" data-testid="coverage-card">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="font-semibold" data-testid="coverage-score">{coverageHeadline(coverage, name)}</p>
        {onBalance && swaps > 0 && (
          <Button onClick={onBalance} disabled={busy} data-testid="balance-button">
            {busy ? 'Adding to the lineup…' : 'Add these to the main lineup'}
          </Button>
        )}
      </div>
      {onBalance && swaps > 0 && (
        <p className="mt-1.5 text-xs text-muted">
          Uses results already on this plan (no new search). Every section keeps at least one crowd-pleaser, and the brief is saved as a new version.
        </p>
      )}
      {onBalance && swaps === 0 && (
        <p className="mt-1.5 text-xs text-muted" data-testid="balance-none">
          {coverage.in_lineup >= coverage.covered ? 'They are already in the main lineup.'
            : 'Nothing more can be moved into the lineup without dropping a pick someone else relies on.'}
        </p>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-warn">{error}</p>}
    </section>
  )
}
