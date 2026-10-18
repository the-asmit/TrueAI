'use client'

import { GitPullRequest, RotateCcw } from 'lucide-react'
import { useId, useState } from 'react'

import { cn } from '@/lib/utils'

/**
 * A real analysis produced by TrueAI during testing (gpt-oss-120b on Groq):
 * a Django view crashed when the optional `discount` query parameter was
 * missing. Timings, confidences, the diff and the review text are that run's.
 * The repository name is illustrative.
 */
export const EXAMPLE = {
  error: 'TypeError',
  message: "int() argument must be a string, a bytes-like object or a real number, not 'NoneType'",
  location: 'shop/views.py:8 in order_total',
  rootCause: 'order_total calls int() on the optional “discount” query parameter, which is None when the parameter is omitted.',
  rootConfidence: 0.96,
  reviewConfidence: 0.92,
  review: 'Supplies a default of “0” for the missing parameter, so int() never receives None; valid discounts behave exactly as before.',
  prTitle: 'Handle missing discount query parameter in order_total view',
  steps: [
    { time: '18:52:04', who: 'Error received', what: 'TypeError from Sentry', tone: 'muted' },
    { time: '18:52:07', who: 'Classified', what: 'Code bug · high severity', tone: 'ok' },
    { time: '18:52:07', who: 'Code read', what: 'shop/views.py at the deployed commit', tone: 'muted' },
    { time: '18:52:09', who: 'Root cause', what: 'Found · 96% confidence', tone: 'ok' },
    { time: '18:52:11', who: 'Fix written', what: '1 edit, risk low · checked', tone: 'ok' },
    { time: '18:52:13', who: 'Reviewed', what: 'Approved · 92% confidence', tone: 'ok' },
    { time: '18:52:13', who: 'Pull request', what: 'Opened, waiting for your review', tone: 'review' },
  ],
  diff: [
    { kind: 'ctx', no: 5, text: 'def order_total(request, order_id):' },
    { kind: 'ctx', no: 6, text: '    order = Order.objects.get(id=order_id)' },
    { kind: 'del', no: 7, text: '    discount = request.GET.get("discount")' },
    { kind: 'add', no: 7, text: '    discount = request.GET.get("discount", "0")' },
    { kind: 'ctx', no: 8, text: '    total = order.subtotal - order.subtotal * (int(discount) / 100)' },
  ],
} as const

const TONE_DOT: Record<string, string> = { ok: 'bg-fixed', review: 'bg-review', muted: 'bg-rule-strong' }

/** Figure 1 on the landing page: the report writes itself, one entry at a time. */
/** ``compact`` leaves out the code change, for narrow or short spaces. */
export function ExampleReport({ className, compact = false }: { className?: string; compact?: boolean }) {
  const captionId = useId()
  const [run, setRun] = useState(0)
  const delay = (index: number) => ({ animationDelay: `${200 + index * 250}ms` })
  const afterSteps = EXAMPLE.steps.length

  return (
    <figure className={cn('overflow-hidden rounded-lg border border-rule bg-sheet shadow-[var(--shadow-sheet)]', className)} aria-labelledby={captionId}>
      <div className="flex items-center justify-between gap-3 border-b border-rule px-5 py-3">
        <p className="text-[0.75rem] text-ink-3">
          Incident report · <span className="font-mono">shop</span> · production
        </p>
        <button
          type="button"
          onClick={() => setRun((value) => value + 1)}
          className="inline-flex items-center gap-1.5 rounded text-[0.75rem] text-ink-3 hover:text-ink"
          aria-label="Replay the example"
        >
          <RotateCcw className="size-3.5" aria-hidden /> Replay
        </button>
      </div>

      <div key={run} className="px-5 py-5">
        <p className="font-mono text-[1.125rem] font-semibold text-ink">{EXAMPLE.error}</p>
        <p className="mt-1 text-[0.8125rem] leading-relaxed text-ink-2">{EXAMPLE.message}</p>
        <p className="mt-1 font-mono text-[0.75rem] text-ink-3">{EXAMPLE.location}</p>

        <ol className="mt-5 border-t border-rule" aria-label="Timeline, UTC">
          {EXAMPLE.steps.map((step, index) => (
            <li key={index} className="set-in grid grid-cols-[4.25rem_7rem_1fr] items-baseline gap-2 border-b border-rule py-1.5 text-[0.8125rem]" style={delay(index)}>
              <time className="tabular font-mono text-[0.75rem] text-ink-3">{step.time}</time>
              <span className="flex items-center gap-2 font-medium text-ink">
                <span aria-hidden className={cn('size-1.5 shrink-0 rounded-[1px]', TONE_DOT[step.tone])} />
                {step.who}
              </span>
              <span className="text-ink-2">{step.what}</span>
            </li>
          ))}
        </ol>

        <div className="set-in mt-5" style={delay(afterSteps)}>
          <p className="text-[0.75rem] text-ink-3">Root cause · {Math.round(EXAMPLE.rootConfidence * 100)}%</p>
          <p className="mt-1 text-[0.875rem] font-medium leading-relaxed text-ink">{EXAMPLE.rootCause}</p>
        </div>

        {!compact && (
          <div className="set-in mt-4 overflow-x-auto rounded-md border border-rule" style={delay(afterSteps + 1)}>
            <p className="border-b border-rule bg-sunken/70 px-3 py-1.5 font-mono text-[0.75rem] text-ink-2">shop/views.py</p>
            <table className="w-full border-collapse font-mono text-[0.75rem] leading-[1.7]">
              <tbody>
                {EXAMPLE.diff.map((line, index) => (
                  <tr key={index} className={line.kind === 'add' ? 'bg-diff-add text-diff-add-ink' : line.kind === 'del' ? 'bg-diff-del text-diff-del-ink' : 'text-ink-2'}>
                    <td className="w-8 select-none px-2 text-right text-ink-3/80">{line.no}</td>
                    <td className="w-4 select-none text-center" aria-hidden>
                      {line.kind === 'add' ? '+' : line.kind === 'del' ? '−' : ''}
                    </td>
                    <td className="whitespace-pre pr-3">{line.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="set-in mt-4 flex items-start gap-3 rounded-md bg-review-tint px-3.5 py-3" style={delay(afterSteps + 2)}>
          <GitPullRequest className="mt-0.5 size-4 shrink-0 text-review" aria-hidden />
          <div className="min-w-0">
            <p className="text-[0.8125rem] font-semibold text-ink">{EXAMPLE.prTitle}</p>
            <p className="mt-0.5 text-[0.75rem] leading-relaxed text-ink-2">
              Reviewer approved at {Math.round(EXAMPLE.reviewConfidence * 100)}%: {EXAMPLE.review}
            </p>
          </div>
        </div>
      </div>
      <figcaption id={captionId} className="border-t border-rule px-5 py-2.5 text-[0.75rem] text-ink-3">
        Example: a real TrueAI analysis from a test run. Repository name changed.
      </figcaption>
    </figure>
  )
}
