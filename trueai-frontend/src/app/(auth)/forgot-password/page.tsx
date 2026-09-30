'use client'

import Link from 'next/link'
import { useState, type FormEvent } from 'react'

import { friendlyAuthError } from '@/components/auth/password-input'
import { Button } from '@/components/ui/button'
import { Field, Input } from '@/components/ui/field'
import { Notice } from '@/components/ui/notice'
import { createClient } from '@/lib/supabase/client'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    const supabase = createClient()
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), {
      redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`,
    })
    setPending(false)
    // Only rate limits and outages are shown; unknown emails look identical to known ones.
    if (resetError && /rate|security|network|fetch/i.test(resetError.message)) {
      setError(friendlyAuthError(resetError.message))
      return
    }
    setSent(true)
  }

  return (
    <div>
      <h1 className="text-[1.625rem] font-bold tracking-[-0.02em] text-ink">Reset your password</h1>
      {sent ? (
        <>
          <p className="mt-2 text-sm leading-relaxed text-ink-2">
            If an account exists for <span className="font-medium text-ink">{email.trim()}</span>, a reset link is on its way. It expires in one hour.
          </p>
          <p className="mt-6 text-sm">
            <Link href="/login" className="font-medium text-ink underline underline-offset-4">
              Back to sign in
            </Link>
          </p>
        </>
      ) : (
        <>
          <p className="mt-1.5 text-sm text-ink-2">We will email you a link to choose a new password.</p>
          {error && (
            <Notice kind="error" className="mt-6">
              {error}
            </Notice>
          )}
          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            <Field id="email" label="Email">
              <Input id="email" type="email" autoComplete="email" inputMode="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
            </Field>
            <Button type="submit" size="lg" className="w-full" loading={pending} disabled={!email.trim()}>
              Send reset link
            </Button>
          </form>
          <p className="mt-6 text-sm text-ink-2">
            Remembered it?{' '}
            <Link href="/login" className="font-medium text-ink underline underline-offset-4">
              Sign in
            </Link>
          </p>
        </>
      )}
    </div>
  )
}
