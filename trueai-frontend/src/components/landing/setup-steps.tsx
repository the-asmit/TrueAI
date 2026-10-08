'use client'

import { Check } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { GitHubMark, SentryMark } from '@/components/brand'
import { ToneMark } from '@/components/ui/status'
import { cn } from '@/lib/utils'

import { usePlaying } from './use-playing'

/*
 * The landing page's "Running in five minutes" section: the three setup steps,
 * each with a small panel that acts the step out. They play one after another
 * (pick a repository, paste the webhook URL, receive the first fix) while the
 * rule above each step fills like a progress bar, then the sequence repeats.
 *
 * Like the hero's diagram it is ordinary elements and CSS transitions; it starts
 * finished, plays only while on screen, and stays finished under reduced motion.
 */

// The moments of the sequence, in order, and how long each one is held (milliseconds).
const CLEARED = 0 // nothing done yet
const GITHUB_OPEN = 1 // step 1 begins
const REPO_PICKED = 2
const GITHUB_CONNECTED = 3
const SENTRY_OPEN = 4 // step 2 begins
const URL_PASTED = 5
const URL_SAVED = 6
const ERROR_RECEIVED = 7 // step 3 begins
const FIX_READY = 8
const FINISHED = 9
const HOLD = [500, 600, 800, 900, 500, 1000, 800, 1500, 1100, 2800]

const STEPS = [
  { title: 'Connect GitHub', from: GITHUB_OPEN, to: GITHUB_CONNECTED },
  { title: 'Add one URL to Sentry', from: SENTRY_OPEN, to: URL_SAVED },
  { title: 'Get your first fix', from: ERROR_RECEIVED, to: FIX_READY },
]

const REPOSITORIES = ['acme/website', 'acme/shop', 'acme/billing']
const PICKED_REPOSITORY = 'acme/shop'

type StepState = 'idle' | 'active' | 'done'

export function SetupSteps() {
  const rootRef = useRef<HTMLOListElement>(null)
  const playing = usePlaying(rootRef)
  // Start finished, so the picture is complete before (and without) any motion.
  const [moment, setMoment] = useState(FINISHED)

  useEffect(() => {
    if (!playing) return
    const timer = setTimeout(() => setMoment((current) => (current === FINISHED ? CLEARED : current + 1)), HOLD[moment])
    return () => clearTimeout(timer)
  }, [moment, playing])

  const panels = [<GitHubPanel key="github" moment={moment} />, <SentryPanel key="sentry" moment={moment} />, <FirstFixPanel key="fix" moment={moment} />]

  return (
    <ol ref={rootRef} className="grid grid-cols-[minmax(0,1fr)] gap-x-8 gap-y-10 md:grid-cols-3">
      {STEPS.map((step, index) => {
        const state: StepState = moment < step.from ? 'idle' : moment > step.to ? 'done' : 'active'
        // The rule fills for exactly as long as its step plays.
        const duration = HOLD.slice(step.from, step.to + 1).reduce((total, hold) => total + hold, 0)
        const ruleStyle = { '--flow-from': 'translateX(-101%)', '--flow-time': `${duration}ms`, '--flow-ease': 'linear' } as CSSProperties
        return (
          <li key={step.title} className="min-w-0">
            <span aria-hidden data-state={state} style={ruleStyle} className="flow-link block h-0.5 w-full" />
            <p className="mt-5 flex items-center gap-3">
              <StepNumber n={index + 1} state={state} />
              <span className={cn('text-[1.25rem] font-semibold tracking-[-0.01em] transition-colors duration-300', state === 'idle' ? 'text-ink-3' : 'text-ink')}>
                {step.title}
              </span>
            </p>
            <div aria-hidden className="mt-5 h-[9.75rem] overflow-hidden rounded-xl border border-rule bg-sheet px-5 py-4">
              {panels[index]}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** The step's number in a ring; it fills in and becomes a tick when the step is done. */
function StepNumber({ n, state }: { n: number; state: StepState }) {
  return (
    <span
      className={cn(
        'tabular inline-flex size-6 shrink-0 items-center justify-center rounded-full border text-[0.75rem] font-semibold transition-colors duration-300',
        state === 'done' ? 'border-ink bg-ink text-paper' : state === 'active' ? 'border-ink text-ink' : 'border-rule-strong text-ink-3',
      )}
    >
      {state === 'done' ? <Check className="size-3.5" strokeWidth={3} aria-hidden /> : n}
      {state === 'done' && <span className="sr-only">{n}</span>}
    </span>
  )
}

/** Something that sets into place once its moment has come. */
function Appear({ on, className, children }: { on: boolean; className?: string; children: ReactNode }) {
  return (
    <span className={cn('transition-[opacity,transform] duration-300 ease-out', on ? 'opacity-100' : 'translate-y-1 opacity-0 duration-150', className)}>
      {children}
    </span>
  )
}

function PanelHeader({ icon, label, done, doneLabel }: { icon: ReactNode; label: string; done: boolean; doneLabel: string }) {
  return (
    <p className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-2 text-[0.8125rem] font-semibold text-ink">
        {icon} {label}
      </span>
      <Appear on={done} className="flex items-center gap-1 text-[0.75rem] font-medium text-fixed">
        <Check className="size-3.5" strokeWidth={2.75} /> {doneLabel}
      </Appear>
    </p>
  )
}

/** Step 1: a repository is picked from the list. */
function GitHubPanel({ moment }: { moment: number }) {
  return (
    <>
      <PanelHeader icon={<GitHubMark className="size-4" />} label="Repository" done={moment >= GITHUB_CONNECTED} doneLabel="Connected" />
      <ul className="mt-2.5 space-y-0.5 font-mono text-[0.75rem]">
        {REPOSITORIES.map((repository) => {
          const picked = repository === PICKED_REPOSITORY && moment >= REPO_PICKED
          return (
            <li key={repository} className={cn('flex items-center gap-2.5 rounded-md px-2 py-1.5 transition-colors duration-300', picked ? 'bg-sunken text-ink' : 'text-ink-2')}>
              <span className={cn('size-3 shrink-0 rounded-full transition-[border-width,border-color] duration-300', picked ? 'border-4 border-ink' : 'border border-rule-strong')} />
              {repository}
              <Appear on={picked} className="ml-auto font-sans text-ink-3">
                main
              </Appear>
            </li>
          )
        })}
      </ul>
    </>
  )
}

/** Step 2: the webhook URL is pasted into Sentry and saved. */
function SentryPanel({ moment }: { moment: number }) {
  const saved = moment >= URL_SAVED
  return (
    <>
      <PanelHeader icon={<SentryMark className="size-4" />} label="Webhook URL" done={saved} doneLabel="Saved" />
      <p
        className={cn(
          'mt-3 flex h-9 items-center rounded-md border bg-paper px-2.5 font-mono text-[0.75rem] text-ink transition-colors duration-300',
          moment >= SENTRY_OPEN && !saved ? 'border-focus' : 'border-rule-strong',
        )}
      >
        <span data-on={moment >= URL_PASTED} className="flow-wipe truncate">
          https://…/webhook/sentry?key=tai_••••••••
        </span>
      </p>
      <p className="mt-3 flex items-center gap-2.5 text-[0.8125rem] text-ink-2">
        <span
          className={cn(
            'inline-flex size-3.5 shrink-0 items-center justify-center rounded-[3px] border transition-colors duration-300',
            saved ? 'border-ink bg-ink text-paper' : 'border-rule-strong',
          )}
        >
          {saved && <Check className="size-3" strokeWidth={3.5} />}
        </span>
        Send new issues to TrueAI
      </p>
    </>
  )
}

/** Step 3: the first error arrives and comes back as a pull request. */
function FirstFixPanel({ moment }: { moment: number }) {
  if (moment < ERROR_RECEIVED) {
    return <p className="flex h-full items-center justify-center text-[0.8125rem] text-ink-3">Waiting for the next error</p>
  }
  const fixed = moment >= FIX_READY
  return (
    <div className="set-in">
      <p className="flex items-center justify-between gap-3">
        <span className="font-mono text-[0.875rem] font-semibold text-ink">TypeError</span>
        {fixed ? (
          <ToneMark tone="review" label="Pull request open" className="text-[0.75rem]" />
        ) : (
          <ToneMark tone="working" label="Analysing" className="text-[0.75rem]" />
        )}
      </p>
      <p className="mt-1 truncate font-mono text-[0.75rem] text-ink-2">int() argument must be a string, not &apos;NoneType&apos;</p>
      <Appear on={fixed} className="mt-3 flex items-center gap-2 rounded-md bg-fixed-tint px-3 py-2 text-[0.8125rem] text-ink">
        <Check className="size-4 shrink-0 text-fixed" strokeWidth={2.5} />
        <span className="truncate">
          <span className="font-semibold">Fixed.</span> Ready for your review.
        </span>
      </Appear>
    </div>
  )
}
