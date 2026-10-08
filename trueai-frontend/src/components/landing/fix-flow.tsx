'use client'

import { Check, ChevronRight, GitPullRequest, ListChecks, X } from 'lucide-react'
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'

import { SentryMark } from '@/components/brand'
import { cn } from '@/lib/utils'

import { usePlaying } from './use-playing'

/*
 * The landing hero's motion graphic: a flat, three-part diagram that plays one
 * incident at a time. An error arrives from Sentry, the faulty line is found
 * in the code and replaced by the fix, and the result lands on GitHub as a pull
 * request (or as next steps, when code is not the answer). Then the next
 * incident plays.
 *
 * It is drawn with ordinary elements and CSS transitions (no canvas, no video).
 * It pauses while off-screen and shows one finished incident under reduced
 * motion. The incidents illustrate the kinds of errors TrueAI handles.
 */

interface CodeLine {
  no: number
  text: string
  faulty?: boolean
}

interface FlowIncident {
  error: string
  detail: string
  file: string
  lines: CodeLine[]
  /** The line that replaces the faulty one. Absent when code is not the answer. */
  fix?: string
  /** Shown instead of a fix when code is not the answer. */
  note?: string
  outcome: string
  pr?: number
  steps?: number
}

const INCIDENTS: FlowIncident[] = [
  {
    error: 'TypeError',
    detail: "int() argument must be a string, not 'NoneType'",
    file: 'shop/views.py',
    lines: [
      { no: 6, text: 'order = Order.objects.get(id=order_id)' },
      { no: 7, text: 'discount = request.GET.get("discount")', faulty: true },
      { no: 8, text: 'rate = int(discount) / 100' },
    ],
    fix: 'discount = request.GET.get("discount", "0")',
    outcome: 'Default a missing discount to 0',
    pr: 412,
  },
  {
    error: 'TypeError',
    detail: "Cannot read properties of undefined (reading 'map')",
    file: 'src/components/OrderHistory.tsx',
    lines: [
      { no: 26, text: 'const { orders } = useOrders()' },
      { no: 27, text: 'return orders.map(renderOrder)', faulty: true },
      { no: 28, text: '}' },
    ],
    fix: 'return (orders ?? []).map(renderOrder)',
    outcome: 'Render an empty list while orders load',
    pr: 414,
  },
  {
    error: 'ImproperlyConfigured',
    detail: 'Set the STRIPE_SECRET_KEY environment variable',
    file: 'settings/production.py',
    lines: [
      { no: 63, text: 'STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY")' },
      { no: 64, text: 'STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")', faulty: true },
      { no: 65, text: 'STRIPE_WEBHOOK_KEY = env("STRIPE_WEBHOOK_KEY")' },
    ],
    note: 'The value is missing in production. No code change will fix this.',
    outcome: 'Set STRIPE_SECRET_KEY in production',
    steps: 2,
  },
]

// The steps of one incident, in order, and how long each one is held (milliseconds).
const CLEARED = 0 // everything hidden, ready for the next incident
const ARRIVED = 1 // the error card is in
const TRACING = 2 // the code is open and the faulty line is marked
const RESOLVED = 3 // the fix (or the "not a code bug" note) is written
const REVIEWED = 4 // the fix is checked
const DELIVERED = 5 // the pull request (or next steps) is out
const HOLD = [350, 1000, 1500, 1500, 1100, 3400]

export function FixFlow({ className }: { className?: string }) {
  const rootRef = useRef<HTMLDivElement>(null)
  const playing = usePlaying(rootRef)
  // Start on a finished incident, so the picture is complete before (and without) any motion.
  const [scene, setScene] = useState({ incident: 0, step: DELIVERED })

  useEffect(() => {
    if (!playing) return
    const timer = setTimeout(() => {
      setScene(({ incident, step }) =>
        step === DELIVERED ? { incident: (incident + 1) % INCIDENTS.length, step: CLEARED } : { incident, step: step + 1 },
      )
    }, HOLD[scene.step])
    return () => clearTimeout(timer)
  }, [scene, playing])

  const incident = INCIDENTS[scene.incident]
  const { step } = scene

  return (
    <div
      ref={rootRef}
      role="img"
      aria-label="Illustration: an error from Sentry is traced to the faulty line of code, fixed, and opened as a pull request on GitHub."
      className={cn('relative text-left', className)}
    >
      <div aria-hidden className="dot-grid absolute -inset-x-6 -inset-y-10" />
      <div
        aria-hidden
        className="relative mx-auto grid max-w-md grid-cols-1 items-center lg:max-w-none lg:grid-cols-[minmax(0,1fr)_4rem_minmax(0,1.5fr)_4rem_minmax(0,1fr)]"
      >
        <Slot label="Sentry error" className="h-[124px]" shown={step >= ARRIVED}>
          <ErrorCard incident={incident} />
        </Slot>

        <FlowLink state={step === TRACING ? 'active' : step > TRACING ? 'done' : 'idle'} />

        <Slot label="Root cause and fix" className="h-[196px]" shown={step >= TRACING}>
          <CodePanel incident={incident} step={step} />
        </Slot>

        <FlowLink state={step === DELIVERED ? 'active' : 'idle'} />

        <Slot label={incident.steps ? 'For you' : 'On GitHub'} className="h-[124px]" shown={step >= DELIVERED}>
          <OutcomeCard incident={incident} />
        </Slot>
      </div>
    </div>
  )
}

/** A place in the diagram: a dashed outline that its card sets into. */
function Slot({ label, shown, className, children }: { label: string; shown: boolean; className?: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-[0.75rem] text-stage-ink-2">{label}</p>
      <div className={cn('relative rounded-lg border border-dashed border-stage-ink/20', className)}>
        <div
          className={cn(
            '-m-px absolute inset-0 overflow-hidden rounded-lg border border-rule bg-sheet shadow-[var(--shadow-sheet)] transition-[opacity,transform] duration-500 ease-out',
            shown ? 'opacity-100' : 'translate-y-2 opacity-0 duration-200',
          )}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

/** The line between two slots. It fills as the work moves along it. */
function FlowLink({ state }: { state: 'idle' | 'active' | 'done' }) {
  return (
    <div className="flex flex-col items-center py-1.5 lg:flex-row lg:px-2 lg:pb-0 lg:pt-[1.625rem]">
      <span data-state={state} className="flow-link block h-7 w-px lg:h-px lg:w-full" />
      <ChevronRight
        className={cn('-mt-1.5 size-3.5 shrink-0 rotate-90 transition-colors duration-500 lg:-ml-1.5 lg:mt-0 lg:rotate-0', state === 'idle' ? 'text-rule-strong' : 'text-ink')}
        strokeWidth={2.25}
      />
    </div>
  )
}

function ErrorCard({ incident }: { incident: FlowIncident }) {
  return (
    <div className="flex h-full flex-col justify-between px-4 py-3.5">
      <div className="min-w-0">
        <p className="flex items-center gap-2 font-mono text-[0.875rem] font-semibold text-failure">
          <X className="size-4 shrink-0" strokeWidth={2.75} />
          <span className="truncate">{incident.error}</span>
        </p>
        <p className="mt-1.5 line-clamp-2 font-mono text-[0.75rem] leading-relaxed text-ink-2">{incident.detail}</p>
      </div>
      <p className="flex items-center gap-1.5 text-[0.75rem] text-ink-3">
        <SentryMark className="size-3.5 shrink-0" /> production
      </p>
    </div>
  )
}

function CodePanel({ incident, step }: { incident: FlowIncident; step: number }) {
  const resolved = step >= RESOLVED
  const isFix = Boolean(incident.fix)
  return (
    <div className="flex h-full flex-col">
      <p className="truncate border-b border-rule bg-sunken/70 px-3 py-2 font-mono text-[0.75rem] text-ink-2">{incident.file}</p>

      <div className="flex-1 py-1.5 font-mono text-[0.75rem] leading-[1.9]">
        {incident.lines.map((line) => {
          const marked = line.faulty && step >= TRACING
          const removed = marked && resolved && isFix
          const flagged = marked && resolved && !isFix
          return (
            <Fragment key={line.no}>
              <p
                className={cn(
                  'flex transition-colors duration-500',
                  removed ? 'bg-diff-del text-diff-del-ink' : flagged ? 'bg-human-tint text-ink' : marked ? 'bg-failure-tint text-ink' : 'text-ink-2',
                )}
              >
                <CodeGutter no={line.no} sign={removed ? '−' : ''} />
                <span className="truncate whitespace-pre pr-3">{line.text}</span>
              </p>
              {/* Directly under the faulty line, a row opens for the answer: the fix, or a note when code is not the answer. */}
              {line.faulty && (
                <div className={cn('grid transition-[grid-template-rows] duration-300 ease-out', resolved ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]')}>
                  <p data-on={resolved} className={cn('flow-wipe flex min-h-0 overflow-hidden', isFix ? 'bg-diff-add text-diff-add-ink' : 'font-sans text-human')}>
                    {isFix ? (
                      <>
                        <CodeGutter no={line.no} sign="+" />
                        <span className="truncate whitespace-pre pr-3">{incident.fix}</span>
                      </>
                    ) : (
                      <span className="truncate px-3">{incident.note}</span>
                    )}
                  </p>
                </div>
              )}
            </Fragment>
          )
        })}
      </div>

      <p className="flex items-center gap-2 border-t border-rule px-3 py-2 text-[0.75rem] text-ink-2">
        <PanelStatus step={step} isFix={isFix} />
      </p>
    </div>
  )
}

function CodeGutter({ no, sign }: { no: number; sign: string }) {
  return (
    <>
      <span className="w-9 shrink-0 select-none pr-2 text-right text-ink-3">{no}</span>
      <span className="w-4 shrink-0 select-none">{sign}</span>
    </>
  )
}

function PanelStatus({ step, isFix }: { step: number; isFix: boolean }) {
  if (step < RESOLVED) {
    return (
      <>
        <span className="size-1.5 animate-pulse rounded-full bg-ink-3" /> Finding the root cause
      </>
    )
  }
  if (step < REVIEWED) return <>{isFix ? 'Root cause found. Fix written.' : 'Root cause found. Not a code bug.'}</>
  if (!isFix) {
    return (
      <span className="flex items-center gap-1.5 font-medium text-human">
        <ListChecks className="size-3.5" strokeWidth={2.5} /> Next steps written
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1.5 font-medium text-fixed">
      <Check className="size-3.5" strokeWidth={2.75} /> Reviewed and approved
    </span>
  )
}

function OutcomeCard({ incident }: { incident: FlowIncident }) {
  if (incident.steps) {
    return (
      <div className="flex h-full flex-col justify-between px-4 py-3.5">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[0.875rem] font-semibold text-human">
            <ListChecks className="size-4 shrink-0" strokeWidth={2.5} />
            Next steps ready · {incident.steps}
          </p>
          <p className="mt-1.5 line-clamp-2 text-[0.8125rem] leading-relaxed text-ink">{incident.outcome}</p>
        </div>
        <p className="text-[0.75rem] text-ink-3">No code change needed</p>
      </div>
    )
  }
  return (
    <div className="flex h-full flex-col justify-between px-4 py-3.5">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-[0.875rem] font-semibold text-fixed">
          <Check className="size-4 shrink-0" strokeWidth={2.75} />
          Fixed · pull request #{incident.pr}
        </p>
        <p className="mt-1.5 line-clamp-2 text-[0.8125rem] leading-relaxed text-ink">{incident.outcome}</p>
      </div>
      <p className="flex items-center gap-1.5 text-[0.75rem] text-ink-3">
        <GitPullRequest className="size-3.5 shrink-0" /> Waiting for your review
      </p>
    </div>
  )
}
