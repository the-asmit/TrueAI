import type { IncidentStatus, Severity } from '@/lib/api/types'
import { SEVERITY, STATUS, TONE_DOT, TONE_TEXT, type Tone } from '@/lib/incidents'
import { cn } from '@/lib/utils'

/** A state's single mark: a square pip plus its label. Working states pulse. */
export function ToneMark({ tone, label, className }: { tone: Tone; label: string; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 whitespace-nowrap text-[0.8125rem] font-medium', TONE_TEXT[tone], className)}>
      <span aria-hidden className={cn('size-2 rounded-[2px]', TONE_DOT[tone], tone === 'working' && 'working-dot')} />
      {label}
    </span>
  )
}

export function StatusMark({ status, className }: { status: IncidentStatus; className?: string }) {
  const meta = STATUS[status] ?? { label: status, tone: 'muted' as Tone }
  return <ToneMark tone={meta.tone} label={meta.label} className={className} />
}

/** Severity as a four-step bar: legible at a glance, readable as text by screen readers. */
export function SeverityMark({ severity, className }: { severity: Severity | null; className?: string }) {
  if (!severity) return <span className={cn('text-[0.8125rem] text-ink-3', className)}>—</span>
  const { label, rank } = SEVERITY[severity]
  return (
    <span className={cn('inline-flex items-center gap-2 text-[0.8125rem] text-ink-2', className)}>
      <span aria-hidden className="flex items-end gap-[2px]">
        {[1, 2, 3, 4].map((step) => (
          <span
            key={step}
            className={cn(
              'w-[3px] rounded-[1px]',
              step <= rank ? (rank >= 4 ? 'bg-failure' : rank === 3 ? 'bg-human' : 'bg-ink-2') : 'bg-rule-strong',
            )}
            style={{ height: `${4 + step * 2}px` }}
          />
        ))}
      </span>
      {label}
    </span>
  )
}
