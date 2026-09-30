import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('animate-pulse rounded-sm bg-sunken', className)} />
}

/** An empty state that tells the reader what will appear here and how to get it. */
export function EmptyState({ title, children, action, className }: { title: string; children?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn('rounded-lg border border-dashed border-rule-strong px-6 py-12 text-center', className)}>
      <p className="text-[0.9375rem] font-semibold text-ink">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-2">{children}</div>}
      {action && <div className="mt-5 flex justify-center gap-2">{action}</div>}
    </div>
  )
}

/** A labelled value in a report header block (term / definition). */
export function Meta({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn('min-w-0', className)}>
      <dt className="text-[0.75rem] text-ink-3">{label}</dt>
      <dd className="mt-0.5 truncate text-[0.8125rem] text-ink">{children}</dd>
    </div>
  )
}

/** A section of a report: numbered heading when the order carries meaning. */
export function ReportSection({
  id,
  number,
  title,
  aside,
  children,
  className,
}: {
  id?: string
  number?: string
  title: string
  aside?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section id={id} aria-labelledby={id ? `${id}-title` : undefined} className={cn('scroll-mt-20 border-t border-rule pt-6', className)}>
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h2 id={id ? `${id}-title` : undefined} className="flex items-baseline gap-3 text-[0.9375rem] font-semibold text-ink">
          {number && <span className="tabular text-[0.8125rem] font-normal text-ink-3">{number}</span>}
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  )
}
