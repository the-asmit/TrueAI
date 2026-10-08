'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState, type FormEvent } from 'react'

import { friendlyAuthError, PasswordInput } from '@/components/auth/password-input'
import { Button } from '@/components/ui/button'
import { describedBy, Field } from '@/components/ui/field'
import { Notice } from '@/components/ui/notice'
import { Skeleton } from '@/components/ui/misc'
import { createClient } from '@/lib/supabase/client'

export default function ResetPasswordPage() {
  const router = useRouter()
  const [session, setSession] = useState<'checking' | 'valid' | 'missing'>('checking')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    createClient()
      .auth.getUser()
      .then(({ data }) => setSession(data.user ? 'valid' : 'missing'))
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (password.length < 8) {
      setError('Use at least 8 characters for your password.')
      return
    }
    setPending(true)
    setError(null)
    const { error: updateError } = await createClient().auth.updateUser({ password })
    setPending(false)
    if (updateError) {
      setError(friendlyAuthError(updateError.message))
      return
    }
    router.replace('/dashboard')
    router.refresh()
  }

  if (session === 'checking') {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Checking your reset link">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-72" />
        <Skeleton className="mt-6 h-9 w-full" />
      </div>
    )
  }

  if (session === 'missing') {
    return (
      <div>
        <h1 className="text-[1.625rem] font-bold tracking-[-0.02em] text-ink">This link has expired</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">Reset links work once and for one hour. Request a new one and open it on this device.</p>
        <p className="mt-6">
          <Link href="/forgot-password" className="text-sm font-medium text-ink underline underline-offset-4">
            Request a new link
          </Link>
        </p>
      </div>
    )
  }

  const tooShort = password.length > 0 && password.length < 8
  return (
    <div>
      <h1 className="text-[1.625rem] font-bold tracking-[-0.02em] text-ink">Choose a new password</h1>
      <p className="mt-1.5 text-sm text-ink-2">You will stay signed in on this device.</p>
      {error && (
        <Notice kind="error" className="mt-6">
          {error}
        </Notice>
      )}
      <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
        <Field id="new-password" label="New password" hint="At least 8 characters." error={tooShort ? 'At least 8 characters.' : null}>
          <PasswordInput
            id="new-password"
            autoComplete="new-password"
            autoFocus
            required
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-describedby={describedBy('new-password', tooShort ? 'x' : null)}
            aria-invalid={tooShort || undefined}
          />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={pending}>
          Save password
        </Button>
      </form>
    </div>
  )
}
