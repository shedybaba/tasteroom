import { Button } from './ui'

/** "Add these to the main lineup": moves members' personal picks into the main lineup (existing results only, saved as a new
 *  version). Shown only while a swap is available; the cards above already say who has a pick, and the Compare tab keeps the
 *  coverage numbers, so nothing else is drawn here. */
export default function BalanceButton({ busy, error, onBalance }: { busy: boolean; error: string | null; onBalance: () => void }) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <Button onClick={onBalance} disabled={busy} data-testid="balance-button">
        {busy ? 'Adding to the lineup…' : 'Add these to the main lineup'}
      </Button>
      {error && <p role="alert" className="text-sm text-warn">{error}</p>}
    </div>
  )
}
