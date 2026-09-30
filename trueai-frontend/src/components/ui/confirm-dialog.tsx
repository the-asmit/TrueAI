'use client'

import { Dialog } from 'radix-ui'
import { useState, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'

interface ConfirmDialogProps {
  trigger: ReactNode
  title: string
  description: ReactNode
  confirmLabel: string
  /** When set, the user must type this phrase before confirming (irreversible actions). */
  confirmPhrase?: string
  destructive?: boolean
  onConfirm: () => Promise<string | null | void>
}

/**
 * Confirmation for destructive or irreversible actions only. Focus is trapped,
 * Escape cancels, and the action's own error is shown inside the dialog.
 */
export function ConfirmDialog({ trigger, title, description, confirmLabel, confirmPhrase, destructive, onConfirm }: ConfirmDialogProps) {
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ready = !confirmPhrase || typed.trim() === confirmPhrase

  function reset(next: boolean) {
    setOpen(next)
    if (!next) {
      setTyped('')
      setError(null)
      setPending(false)
    }
  }

  async function confirm() {
    if (!ready || pending) return
    setPending(true)
    setError(null)
    const failure = await onConfirm()
    if (failure) {
      setError(failure)
      setPending(false)
      return
    }
    reset(false)
  }

  return (
    <Dialog.Root open={open} onOpenChange={reset}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/35 data-[state=open]:animate-[fade_150ms_ease-out]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-rule bg-sheet p-6 shadow-[var(--shadow-pop)] focus:outline-none">
          <Dialog.Title className="text-base font-semibold text-ink">{title}</Dialog.Title>
          <Dialog.Description asChild>
            <div className="mt-2 text-sm leading-relaxed text-ink-2">{description}</div>
          </Dialog.Description>
          {confirmPhrase && (
            <div className="mt-4 space-y-1.5">
              <label htmlFor="confirm-phrase" className="block text-[0.8125rem] text-ink-2">
                Type <span className="font-mono text-ink">{confirmPhrase}</span> to confirm
              </label>
              <Input
                id="confirm-phrase"
                autoComplete="off"
                spellCheck={false}
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && confirm()}
              />
            </div>
          )}
          {error && (
            <p role="alert" className="mt-4 text-[0.8125rem] text-failure">
              {error}
            </p>
          )}
          <div className="mt-6 flex justify-end gap-2">
            <Dialog.Close asChild>
              <Button variant="ghost">Cancel</Button>
            </Dialog.Close>
            <Button variant={destructive ? 'danger' : 'primary'} disabled={!ready} loading={pending} onClick={confirm}>
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
