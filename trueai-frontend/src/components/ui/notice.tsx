import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Kind = 'info' | 'success' | 'warning' | 'error'

const styles: Record<Kind, { box: string; icon: ReactNode }> = {
  info: { box: 'bg-review-tint text-ink', icon: <Info className="text-review" /> },
  success: { box: 'bg-fixed-tint text-ink', icon: <CircleCheck className="text-fixed" /> },
  warning: { box: 'bg-human-tint text-ink', icon: <TriangleAlert className="text-human" /> },
  error: { box: 'bg-failure-tint text-ink', icon: <CircleAlert className="text-failure" /> },
}

/** Inline, in-context feedback. Errors are announced to assistive technology. */
export function Notice({
  kind = 'info',
  title,
  children,
  action,
  className,
}: {
  kind?: Kind
  title?: string
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  const { box, icon } = styles[kind]
  return (
    <div
      role={kind === 'error' ? 'alert' : 'status'}
      className={cn('flex items-start gap-3 rounded-md px-3.5 py-3 text-[0.8125rem] leading-relaxed [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0', box, className)}
    >
      {icon}
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn('text-ink-2', title && 'mt-0.5')}>{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
