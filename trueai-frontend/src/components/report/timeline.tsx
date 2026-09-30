import { Prose } from '@/components/report/prose'
import type { PipelineStep } from '@/lib/api/types'
import { formatDuration, formatUtcTime } from '@/lib/format'
import { STEP_LABEL, STEP_STATUS_TONE, TONE_DOT, TONE_TEXT } from '@/lib/incidents'
import { cn } from '@/lib/utils'

const STATUS_WORD: Record<PipelineStep['status'], string> = {
  running: 'Running',
  ok: 'Done',
  warning: 'Attention',
  error: 'Failed',
  skipped: 'Skipped',
}

/**
 * The run's log: one entry per agent or tool step, in order, with its exact
 * UTC time, the model that ran it and what it concluded.
 */
export function Timeline({ steps, live = false }: { steps: PipelineStep[]; live?: boolean }) {
  if (steps.length === 0) {
    return <p className="text-sm text-ink-3">{live ? 'Waiting for the first step…' : 'No steps were recorded for this run.'}</p>
  }
  return (
    <ol className="relative space-y-0">
      {steps.map((step, index) => {
        const tone = STEP_STATUS_TONE[step.status]
        const tokens = (step.input_tokens ?? 0) + (step.output_tokens ?? 0)
        return (
          <li key={step.id} className={cn('grid grid-cols-[4.5rem_1fr] gap-x-4 py-3', index > 0 && 'border-t border-rule', live && index === steps.length - 1 && 'set-in')}>
            <time dateTime={step.created_at} className="tabular pt-px font-mono text-[0.75rem] text-ink-3" title="UTC">
              {formatUtcTime(step.created_at)}
            </time>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-[0.8125rem] font-semibold text-ink">{STEP_LABEL[step.step] ?? step.step}</span>
                <span className={cn('inline-flex items-center gap-1.5 text-[0.75rem]', TONE_TEXT[tone])}>
                  <span aria-hidden className={cn('size-1.5 rounded-[1px]', TONE_DOT[tone])} />
                  {STATUS_WORD[step.status]}
                </span>
                {step.model && <span className="font-mono text-[0.75rem] text-ink-3">{step.model}</span>}
              </div>
              {step.summary && (
                <p className="mt-1 max-w-[75ch] text-[0.8125rem] leading-relaxed text-ink-2">
                  <Prose text={step.summary} />
                </p>
              )}
              {(step.duration_ms || tokens > 0) && (
                <p className="tabular mt-1 text-[0.75rem] text-ink-3">
                  {step.duration_ms ? formatDuration(step.duration_ms) : null}
                  {step.duration_ms && tokens > 0 ? ' · ' : null}
                  {tokens > 0 ? `${tokens.toLocaleString('en-GB')} tokens` : null}
                </p>
              )}
            </div>
          </li>
        )
      })}
      {live && (
        <li className="grid grid-cols-[4.5rem_1fr] gap-x-4 border-t border-rule py-3" aria-live="polite">
          <span />
          <span className="inline-flex items-center gap-2 text-[0.8125rem] text-ink-2">
            <span aria-hidden className="working-dot size-1.5 rounded-[1px] bg-ink-3" />
            Working…
          </span>
        </li>
      )}
    </ol>
  )
}
