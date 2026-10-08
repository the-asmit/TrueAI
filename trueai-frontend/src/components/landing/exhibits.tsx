import { Check, GitPullRequest } from 'lucide-react'
import type { ReactNode } from 'react'

import { ToneMark } from '@/components/ui/status'
import { cn } from '@/lib/utils'

/*
 * The landing page's figures. Each one is the product's own output, condensed
 * from real TrueAI runs and labelled as an example: they show what a visitor
 * gets instead of describing it.
 */

const DIFF = [
  { no: 5, kind: 'context', text: 'def order_total(request, order_id):' },
  { no: 6, kind: 'context', text: '    order = Order.objects.get(id=order_id)' },
  { no: 7, kind: 'del', text: '    discount = request.GET.get("discount")' },
  { no: 7, kind: 'add', text: '    discount = request.GET.get("discount", "0")' },
  { no: 8, kind: 'context', text: '    total = order.subtotal - order.subtotal * (int(discount) / 100)' },
] as const

/** A numbered marker tying a part of the report to its note in the margin. */
function Marker({ n, className }: { n: number; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        'tabular inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-ink text-[0.75rem] font-semibold text-ink',
        className,
      )}
    >
      {n}
    </span>
  )
}

const ANSWER_NOTES = ['What went wrong, in plain English', 'The smallest change that fixes it', 'A second opinion', 'A pull request, waiting for you']

export function AnswerExhibit() {
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_17rem] lg:gap-12">
      <figure aria-labelledby="answer-caption" className="reveal overflow-hidden rounded-xl border border-rule bg-sheet shadow-[var(--shadow-sheet)]">
        <div className="border-b border-rule px-5 py-5 sm:px-7">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="font-mono text-[1.125rem] font-semibold text-ink">TypeError</p>
            <span className="flex items-center gap-2.5">
              <ToneMark tone="review" label="Pull request open" />
              <Marker n={4} />
            </span>
          </div>
          <p className="mt-1 text-[0.875rem] leading-relaxed text-ink-2">
            int() argument must be a string, a bytes-like object or a real number, not &apos;NoneType&apos;
          </p>
          <p className="mt-1 font-mono text-[0.75rem] text-ink-3">shop/views.py:8 in order_total</p>
        </div>

        <div className="space-y-6 px-5 py-6 sm:px-7">
          <div className="flex gap-3">
            <Marker n={1} className="mt-1" />
            <div className="min-w-0">
              <p className="text-[0.75rem] text-ink-3">Root cause · 96% confidence</p>
              <p className="mt-1 max-w-[52ch] text-[1.125rem] font-semibold leading-snug tracking-[-0.01em] text-ink">
                order_total passes “discount” straight to int(), and it is missing when a customer has no code.
              </p>
            </div>
          </div>

          <div className="flex gap-3">
            <Marker n={2} className="mt-2" />
            <div className="min-w-0 flex-1 overflow-hidden rounded-lg border border-rule">
              <p className="border-b border-rule bg-sunken/70 px-3 py-1.5 font-mono text-[0.75rem] text-ink-2">shop/views.py</p>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse font-mono text-[0.75rem] leading-[1.8]">
                  <tbody>
                    {DIFF.map((line, index) => (
                      <tr
                        key={index}
                        className={line.kind === 'add' ? 'bg-diff-add text-diff-add-ink' : line.kind === 'del' ? 'bg-diff-del text-diff-del-ink' : 'text-ink-2'}
                      >
                        <td className="w-8 select-none px-2 text-right text-ink-3/80">{line.no}</td>
                        <td className="w-4 select-none text-center" aria-hidden>
                          {line.kind === 'add' ? '+' : line.kind === 'del' ? '−' : ''}
                        </td>
                        <td className="whitespace-pre pr-4">{line.text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="flex gap-3">
            <Marker n={3} className="mt-2.5" />
            <div className="flex min-w-0 flex-1 items-start gap-3 rounded-lg bg-fixed-tint px-4 py-3">
              <Check className="mt-0.5 size-4 shrink-0 text-fixed" strokeWidth={2.5} aria-hidden />
              <p className="text-[0.8125rem] leading-relaxed text-ink-2">
                <span className="font-semibold text-ink">Double-checked and approved · 92%.</span> Real discount codes work exactly as
                before.
              </p>
            </div>
          </div>
        </div>

        <figcaption id="answer-caption" className="border-t border-rule px-5 py-2.5 text-[0.75rem] text-ink-3 sm:px-7">
          Example: condensed from a real TrueAI analysis.
        </figcaption>
      </figure>

      <ol className="grid content-start gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-1 lg:pt-6">
        {ANSWER_NOTES.map((note, index) => (
          <li key={note} className="flex gap-3">
            <Marker n={index + 1} className="mt-0.5" />
            <p className="text-[0.9375rem] font-semibold text-ink">{note}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}

const HANDOVER_STEPS = [
  'Check that PostgreSQL is running on db.internal.',
  'Confirm it listens on port 5432, not only on localhost.',
  'Restart the service and load the orders page to confirm.',
]

export function HandoverExhibit() {
  return (
    <figure aria-labelledby="handover-caption" className="reveal overflow-hidden rounded-xl border border-rule bg-sheet shadow-[var(--shadow-sheet)]">
      <div className="border-b border-rule px-5 py-5 sm:px-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-mono text-[1.125rem] font-semibold text-ink">OperationalError</p>
          <ToneMark tone="human" label="Needs you" />
        </div>
        <p className="mt-1 text-[0.875rem] leading-relaxed text-ink-2">could not connect to server: Connection refused (db.internal:5432)</p>
        <p className="mt-3 text-[0.8125rem] text-ink-3">Infrastructure · no code change will fix this</p>
      </div>
      <div className="px-5 py-5 sm:px-7">
        <p className="text-[0.8125rem] font-semibold text-ink">Next steps for this incident</p>
        <ol className="mt-3 space-y-3">
          {HANDOVER_STEPS.map((step) => (
            <li key={step} className="flex items-start gap-3 text-[0.875rem] leading-relaxed text-ink-2">
              <span aria-hidden className="mt-[0.3rem] size-3.5 shrink-0 rounded-[3px] border border-rule-strong bg-sheet" />
              {step}
            </li>
          ))}
        </ol>
      </div>
      <figcaption id="handover-caption" className="border-t border-rule px-5 py-2.5 text-[0.75rem] text-ink-3 sm:px-7">
        Example: condensed from a real TrueAI run.
      </figcaption>
    </figure>
  )
}

/** A small illustrative panel in the "you stay in charge" row. */
function Panel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <figure aria-label={label} className="reveal flex h-[11.5rem] flex-col justify-center overflow-hidden rounded-xl border border-rule bg-sheet px-5">
      {children}
    </figure>
  )
}

export function MergePanel() {
  return (
    <Panel label="Example: a TrueAI pull request waiting for your review">
      <p className="flex min-w-0 items-center gap-2 text-[0.8125rem] font-semibold text-ink">
        <GitPullRequest className="size-4 shrink-0 text-review" aria-hidden />
        <span className="truncate">Default a missing discount to 0</span>
        <span className="shrink-0 font-mono font-normal text-ink-3">#412</span>
      </p>
      <p className="mt-3 flex items-center gap-1.5 text-[0.75rem] font-medium text-fixed">
        <Check className="size-3.5" strokeWidth={2.5} aria-hidden /> Reviewed and approved by TrueAI
      </p>
      <ToneMark tone="human" label="Waiting for your review" className="mt-1.5 text-[0.75rem]" />
      <p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span aria-hidden className="inline-flex h-8 items-center rounded-md bg-action px-3 text-[0.8125rem] font-medium text-on-action">
          Merge pull request
        </span>
        <span className="text-[0.75rem] text-ink-3">Only you can press this.</span>
      </p>
    </Panel>
  )
}

const RECORD = [
  ['03:12:04', 'Error received', 'TypeError'],
  ['03:12:06', 'Classified', 'Code bug · high'],
  ['03:12:09', 'Root cause found', '96% sure'],
  ['03:12:13', 'Fix written', 'One edit, checked'],
  ['03:12:15', 'Change approved', '92% sure'],
] as const

export function RecordPanel() {
  return (
    <Panel label="Example: the step-by-step record TrueAI keeps for every incident">
      <ol className="space-y-1.5">
        {RECORD.map(([time, step, detail]) => (
          <li key={step} className="grid grid-cols-[4.25rem_7.25rem_minmax(0,1fr)] items-baseline gap-2 text-[0.75rem]">
            <time className="tabular font-mono text-ink-3">{time}</time>
            <span className="font-medium text-ink">{step}</span>
            <span className="truncate text-ink-2">{detail}</span>
          </li>
        ))}
      </ol>
    </Panel>
  )
}

const REQUEST = [
  { name: 'Cookie', value: null },
  { name: 'Authorization', value: null },
  { name: 'email', value: null },
  { name: 'User-Agent', value: 'Mozilla/5.0 (Macintosh)' },
  { name: 'path', value: '/checkout/summary' },
]

export function PrivacyPanel() {
  return (
    <Panel label="Example: private request data removed before anything is stored or read by a model">
      <dl className="space-y-1.5 font-mono text-[0.75rem]">
        {REQUEST.map((field) => (
          <div key={field.name} className="grid grid-cols-[6.75rem_minmax(0,1fr)] items-center gap-2">
            <dt className="text-ink-3">{field.name}</dt>
            <dd className="min-w-0 truncate text-ink-2">
              {field.value ?? (
                <>
                  <span aria-hidden className="inline-block h-3 w-[70%] max-w-[9rem] rounded-[2px] bg-ink align-middle" />
                  <span className="sr-only">removed</span>
                </>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </Panel>
  )
}
