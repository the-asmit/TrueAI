'use client'

import { Check, ListChecks, Pause, Play, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

/*
 * The landing hero's motion graphic: production errors stream toward the
 * viewer on a tilted plane and, as each one crosses the scan line, it turns
 * into its outcome: a pull request, or next steps when code is not the fix.
 *
 * Two identical layers move in lockstep; the "error" layer is clipped to the
 * far side of the scan line and the "fixed" layer to the near side, so every
 * card changes exactly as it crosses. Pure CSS motion (no canvas, no video);
 * it pauses off-screen and on request, and holds still under reduced motion.
 * The incidents are an illustration of the kinds of errors TrueAI handles.
 */

interface StreamIncident {
  error: string
  detail: string
  file: string
  fix?: string
  pr?: number
  steps?: number
}

const COLUMNS: StreamIncident[][] = [
  [
    { error: 'TypeError', detail: "int() argument must be a string, not 'NoneType'", file: 'shop/views.py:8', fix: 'Default a missing discount to 0', pr: 412 },
    { error: 'NoMethodError', detail: "undefined method 'email' for nil", file: 'app/mailers/receipt.rb:19', fix: 'Skip receipts for deleted users', pr: 431 },
    { error: 'OperationalError', detail: 'could not connect to server: Connection refused', file: 'db.internal:5432', steps: 4 },
    { error: 'ValueError', detail: "invalid literal for int() with base 10: ''", file: 'reports/export.py:112', fix: 'Treat blank quantities as zero', pr: 437 },
    { error: 'KeyError', detail: "'currency'", file: 'shop/views/checkout.py:41', fix: 'Fall back to the store currency', pr: 413 },
    { error: 'TypeError', detail: "Cannot read properties of null (reading 'id')", file: 'src/hooks/useSession.ts:23', fix: 'Wait for the session before reading it', pr: 444 },
  ],
  [
    { error: 'TypeError', detail: "Cannot read properties of undefined (reading 'map')", file: 'src/components/OrderHistory.tsx:27', fix: 'Render an empty list while orders load', pr: 414 },
    { error: 'ImproperlyConfigured', detail: 'Set the STRIPE_SECRET_KEY environment variable', file: 'settings/production.py:64', steps: 2 },
    { error: 'NullPointerException', detail: 'Cannot invoke "Address.getCity()" on null', file: 'ShippingService.java:88', fix: 'Handle orders without an address', pr: 426 },
    { error: 'IntegrityError', detail: 'duplicate key value violates unique constraint', file: 'accounts/signup.py:57', fix: 'Reuse the account on repeat sign-ups', pr: 439 },
    { error: 'RangeError', detail: 'Invalid time value', file: 'src/lib/format.ts:14', fix: 'Show a dash for missing dates', pr: 441 },
    { error: 'ZeroDivisionError', detail: 'division by zero', file: 'billing/usage.py:203', fix: 'Skip empty billing periods', pr: 446 },
  ],
  [
    { error: 'panic', detail: 'runtime error: invalid memory address or nil pointer', file: 'worker/queue.go:57', fix: 'Guard the empty-queue case', pr: 418 },
    { error: 'AttributeError', detail: "'NoneType' object has no attribute 'strip'", file: 'imports/csv.py:36', fix: 'Ignore rows without a name', pr: 433 },
    { error: 'SyntaxError', detail: 'Unexpected token < in JSON at position 0', file: 'src/api/client.ts:48', fix: 'Report HTML error pages clearly', pr: 428 },
    { error: 'TimeoutError', detail: 'Redis connection timed out after 5000ms', file: 'cache.internal:6379', steps: 3 },
    { error: 'IndexError', detail: 'list index out of range', file: 'search/rank.py:91', fix: 'Return no results for empty queries', pr: 435 },
    { error: 'TypeError', detail: "unsupported operand type(s) for +: 'int' and 'str'", file: 'cart/totals.py:22', fix: 'Parse quantities before adding', pr: 442 },
  ],
  [
    { error: 'UnhandledPromiseRejection', detail: 'fetch failed: ECONNRESET', file: 'src/jobs/webhooks.ts:65', fix: 'Retry webhook deliveries once', pr: 421 },
    { error: 'KeyError', detail: "'shipping_method'", file: 'orders/serializers.py:74', fix: 'Default to standard shipping', pr: 430 },
    { error: 'DoesNotExist', detail: 'Coupon matching query does not exist', file: 'promotions/apply.py:29', fix: 'Reject unknown coupons politely', pr: 436 },
    { error: 'PermissionError', detail: "[Errno 13] Permission denied: '/var/uploads'", file: 'uploads/storage.py:18', steps: 3 },
    { error: 'TypeError', detail: "Cannot destructure property 'user' of undefined", file: 'src/pages/profile.tsx:12', fix: 'Load the profile before rendering', pr: 440 },
    { error: 'ValueError', detail: 'time data "" does not match format', file: 'events/parse.py:47', fix: 'Skip events without a timestamp', pr: 447 },
  ],
]

// Seconds for one full cycle of each column: slightly different, so the columns drift against each other.
const DURATIONS = [42, 50, 38, 46]

// Where the scan line sits, as a fraction of the plane's height (0 = far edge, 1 = near edge). The stylesheet may
// override --scan for small screens; the fallback here keeps the layers split even without that rule.
const SCAN = 'var(--scan, 0.44)'

export function FixStream({ className }: { className?: string }) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [paused, setPaused] = useState(false)
  const [offscreen, setOffscreen] = useState(false)

  useEffect(() => {
    const node = rootRef.current
    if (!node) return
    const observer = new IntersectionObserver(([entry]) => setOffscreen(!entry.isIntersecting))
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={rootRef} className={cn('fix-stream relative', className)} data-paused={paused || offscreen}>
      <div aria-hidden className="fix-stream-viewport absolute inset-0 overflow-hidden">
        <div className="fix-stream-plane">
          <StreamLayer kind="error" />
          <StreamLayer kind="fixed" />
          <div className="fix-stream-scan" style={{ top: `calc(${SCAN} * 100%)` }} />
        </div>
      </div>
      <button
        type="button"
        onClick={() => setPaused((value) => !value)}
        aria-pressed={paused}
        aria-label={paused ? 'Play the illustration' : 'Pause the illustration'}
        className="absolute bottom-4 right-4 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[0.75rem] text-stage-ink-2 transition-colors hover:bg-white/5 hover:text-stage-ink focus-visible:outline-stage-ink sm:bottom-6 sm:right-8"
      >
        {paused ? <Play className="size-3.5" aria-hidden /> : <Pause className="size-3.5" aria-hidden />}
        {paused ? 'Play' : 'Pause'}
      </button>
    </div>
  )
}

/** One full set of columns. The error layer shows the far side of the scan line, the fixed layer the near side. */
function StreamLayer({ kind }: { kind: 'error' | 'fixed' }) {
  const clipPath = kind === 'error' ? `inset(0 0 calc((1 - ${SCAN}) * 100%) 0)` : `inset(calc(${SCAN} * 100%) 0 0 0)`
  return (
    <div className="absolute inset-0 grid grid-cols-2 gap-6 px-6 sm:grid-cols-4 sm:gap-8 sm:px-8" style={{ clipPath }}>
      {COLUMNS.map((column, index) => (
        // Phones show the two middle columns only.
        <div key={index} className={cn('stream-col', (index === 0 || index === 3) && 'max-sm:!hidden')} style={{ animationDuration: `${DURATIONS[index]}s` }}>
          {/* Three copies, so the column always covers the plane while it moves by one copy's height. */}
          {[0, 1, 2].map((copy) =>
            column.map((incident, row) =>
              kind === 'error' ? <ErrorCard key={`${copy}-${row}`} incident={incident} /> : <OutcomeCard key={`${copy}-${row}`} incident={incident} />,
            ),
          )}
        </div>
      ))}
    </div>
  )
}

function ErrorCard({ incident }: { incident: StreamIncident }) {
  return (
    <div className="stream-card border-stage-failure/25 bg-stage-failure/[0.07]">
      <p className="flex items-center gap-2 font-mono text-[0.8125rem] font-semibold text-stage-failure">
        <X className="size-3.5 shrink-0" strokeWidth={2.75} />
        <span className="truncate">{incident.error}</span>
      </p>
      <p className="mt-1.5 truncate font-mono text-[0.75rem] text-stage-ink-2">{incident.detail}</p>
      <p className="mt-1 truncate font-mono text-[0.75rem] text-stage-ink-2/60">{incident.file}</p>
    </div>
  )
}

function OutcomeCard({ incident }: { incident: StreamIncident }) {
  if (incident.steps) {
    return (
      <div className="stream-card border-stage-human/30 bg-stage-human/[0.08]">
        <p className="flex items-center gap-2 text-[0.8125rem] font-semibold text-stage-human">
          <ListChecks className="size-3.5 shrink-0" strokeWidth={2.5} />
          Next steps ready · {incident.steps}
        </p>
        <p className="mt-1.5 truncate text-[0.8125rem] text-stage-ink">{incident.error}: no code change needed</p>
        <p className="mt-1 truncate font-mono text-[0.75rem] text-stage-ink-2/60">{incident.file}</p>
      </div>
    )
  }
  return (
    <div className="stream-card border-stage-fixed/30 bg-stage-fixed/[0.08]">
      <p className="flex items-center gap-2 text-[0.8125rem] font-semibold text-stage-fixed">
        <Check className="size-3.5 shrink-0" strokeWidth={2.75} />
        Fixed · pull request #{incident.pr}
      </p>
      <p className="mt-1.5 truncate text-[0.8125rem] text-stage-ink">{incident.fix}</p>
      <p className="mt-1 truncate font-mono text-[0.75rem] text-stage-ink-2/60">{incident.file}</p>
    </div>
  )
}
