import type { ComponentProps, ReactNode } from 'react'

import { cn } from '@/lib/utils'

const control =
  'block w-full rounded-md border border-rule-strong bg-sheet px-3 text-sm text-ink placeholder:text-ink-3 transition-[border-color,box-shadow] duration-150 hover:border-ink-3 focus:border-focus focus:outline-none focus:ring-2 focus:ring-focus/25 disabled:cursor-not-allowed disabled:opacity-55 aria-[invalid=true]:border-failure aria-[invalid=true]:focus:ring-failure/25'

export function Input({ className, ...props }: ComponentProps<'input'>) {
  return <input className={cn(control, 'h-9', className)} {...props} />
}

export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return <textarea className={cn(control, 'min-h-24 py-2', className)} {...props} />
}

export function Select({ className, children, ...props }: ComponentProps<'select'>) {
  return (
    <select className={cn(control, 'h-9 pr-8', className)} {...props}>
      {children}
    </select>
  )
}

interface FieldProps {
  id: string
  label: string
  hint?: ReactNode
  error?: string | null
  optional?: boolean
  children: ReactNode
  className?: string
}

/**
 * Label + control + hint + error, wired together for assistive technology.
 * The control must use ``id`` and should set ``aria-describedby={describedBy(id)}``.
 */
export function Field({ id, label, hint, error, optional, children, className }: FieldProps) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={id} className="flex items-baseline gap-2 text-[0.8125rem] font-medium text-ink">
        {label}
        {optional && <span className="font-normal text-ink-3">Optional</span>}
      </label>
      {children}
      {hint && !error && (
        <p id={`${id}-hint`} className="text-[0.8125rem] text-ink-3">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-[0.8125rem] text-failure">
          {error}
        </p>
      )}
    </div>
  )
}

export function describedBy(id: string, error?: string | null) {
  return error ? `${id}-error` : `${id}-hint`
}
