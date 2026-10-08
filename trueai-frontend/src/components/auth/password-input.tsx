'use client'

import { Eye, EyeOff } from 'lucide-react'
import { useState, type ComponentProps } from 'react'

import { Input } from '@/components/ui/field'

export function PasswordInput(props: Omit<ComponentProps<'input'>, 'type'>) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="relative">
      <Input {...props} type={visible ? 'text' : 'password'} className="pr-10" />
      <button
        type="button"
        onClick={() => setVisible((value) => !value)}
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-ink-3 hover:text-ink"
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
      >
        {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  )
}

/** Supabase auth errors, rewritten for people. */
export function friendlyAuthError(message: string): string {
  const text = message.toLowerCase()
  if (text.includes('invalid login credentials')) return 'Email or password is incorrect.'
  if (text.includes('email not confirmed')) return 'Confirm your email first, using the link we sent when you signed up.'
  if (text.includes('already registered') || text.includes('already been registered')) return 'An account with this email already exists. Sign in instead.'
  if (text.includes('password should be')) return 'Use at least 8 characters for your password.'
  if (text.includes('same as the old password') || text.includes('should be different')) return 'Choose a password different from your current one.'
  if (text.includes('rate limit') || text.includes('security purposes')) return 'Too many attempts. Wait a minute and try again.'
  if (text.includes('network') || text.includes('fetch')) return 'Cannot reach the sign-in service. Check your connection and try again.'
  return message
}
