'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState, type FormEvent } from 'react'

import { friendlyAuthError, PasswordInput } from '@/components/auth/password-input'
import { Button } from '@/components/ui/button'
import { describedBy, Field, Input } from '@/components/ui/field'
import { Notice } from '@/components/ui/notice'
import { createClient } from '@/lib/supabase/client'

export default function SignUpPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [sentTo, setSentTo] = useState<string | null>(null)

  const tooShort = password.length > 0 && password.length < 8

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!email.trim()) {
      setError('Enter your email.')
      return
    }
    if (password.length < 8) {
      setError('Use at least 8 characters for your password.')
      return
    }
    setPending(true)
    setError(null)
    const supabase = createClient()
    const { data, error: authError } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    })
    setPending(false)
    if (authError) {
      setError(friendlyAuthError(authError.message))
      return
    }
    if (data.session) {
      // Email confirmation is off for this project: go straight to setup.
      router.replace('/onboarding')
      router.refresh()
      return
    }
    setSentTo(email.trim())
  }

  if (sentTo) {
    return (
      <div>
        <h1 className="text-[1.625rem] font-bold tracking-[-0.02em] text-ink">Check your email</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">
          We sent a confirmation link to <span className="font-medium text-ink">{sentTo}</span>. Open it on this device to finish creating your account.
        </p>
        <p className="mt-6 text-sm text-ink-2">
          Wrong address?{' '}
          <button type="button" onClick={() => setSentTo(null)} className="font-medium text-ink underline underline-offset-4">
            Start again
          </button>
        </p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-[1.625rem] font-bold tracking-[-0.02em] text-ink">Create your account</h1>
      <p className="mt-1.5 text-sm text-ink-2">Connect Sentry and GitHub in a few minutes.</p>

      {error && (
        <Notice kind="error" className="mt-6">
          {error}
        </Notice>
      )}

      <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
        <Field id="email" label="Work email">
          <Input id="email" type="email" autoComplete="email" inputMode="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <Field id="password" label="Password" hint="At least 8 characters." error={tooShort ? 'At least 8 characters.' : null}>
          <PasswordInput
            id="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-describedby={describedBy('password', tooShort ? 'x' : null)}
            aria-invalid={tooShort || undefined}
          />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={pending}>
          Create account
        </Button>
      </form>

      <p className="mt-7 border-t border-rule pt-5 text-center text-sm text-ink-2">
        Already have an account?{' '}
        <Link href="/login" className="font-medium text-ink underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </div>
  )
}
