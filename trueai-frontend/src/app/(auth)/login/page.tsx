'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useState, type FormEvent } from 'react'

import { friendlyAuthError, PasswordInput } from '@/components/auth/password-input'
import { Button } from '@/components/ui/button'
import { Field, Input } from '@/components/ui/field'
import { Notice } from '@/components/ui/notice'
import { safeNextPath } from '@/lib/redirect'
import { createClient } from '@/lib/supabase/client'

const MESSAGES: Record<string, { kind: 'info' | 'success' | 'error'; text: string }> = {
  signed_out: { kind: 'info', text: 'You are signed out.' },
  link_invalid: { kind: 'error', text: 'That link is invalid or has expired. Request a new one.' },
  deleted: { kind: 'success', text: 'Your account was deleted.' },
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  )
}

function LoginForm() {
  const router = useRouter()
  const params = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [unconfirmed, setUnconfirmed] = useState(false)
  const [resent, setResent] = useState(false)

  const flag = params.get('error') ?? (params.get('signed_out') ? 'signed_out' : null)
  const message = flag ? MESSAGES[flag] : null

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    setUnconfirmed(false)
    const supabase = createClient()
    const { error: authError } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
    if (authError) {
      setPending(false)
      setUnconfirmed(authError.message.toLowerCase().includes('not confirmed'))
      setError(friendlyAuthError(authError.message))
      return
    }
    router.replace(safeNextPath(params.get('next')))
    router.refresh()
  }

  async function resend() {
    const supabase = createClient()
    await supabase.auth.resend({ type: 'signup', email: email.trim(), options: { emailRedirectTo: `${window.location.origin}/auth/callback` } })
    setResent(true)
  }

  return (
    <div>
      <h1 className="text-[1.625rem] font-bold tracking-[-0.02em] text-ink">Sign in</h1>
      <p className="mt-1.5 text-sm text-ink-2">Welcome back. Your incidents are waiting.</p>

      <div className="mt-6 space-y-3">
        {message && <Notice kind={message.kind}>{message.text}</Notice>}
        {error && (
          <Notice
            kind="error"
            action={
              unconfirmed && !resent ? (
                <Button size="sm" variant="secondary" onClick={resend}>
                  Resend link
                </Button>
              ) : undefined
            }
          >
            {resent ? 'A new confirmation link is on its way.' : error}
          </Notice>
        )}
      </div>

      <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
        <Field id="email" label="Email">
          <Input id="email" type="email" autoComplete="email" inputMode="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between">
            <label htmlFor="password" className="text-[0.8125rem] font-medium text-ink">
              Password
            </label>
            <Link href="/forgot-password" className="text-[0.8125rem] text-ink-2 underline-offset-4 hover:text-ink hover:underline">
              Forgot password?
            </Link>
          </div>
          <PasswordInput id="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
        </div>
        <Button type="submit" size="lg" className="w-full" loading={pending} disabled={!email.trim() || !password}>
          Sign in
        </Button>
      </form>

      <p className="mt-6 text-sm text-ink-2">
        New to TrueAI?{' '}
        <Link href="/signup" className="font-medium text-ink underline underline-offset-4">
          Create an account
        </Link>
      </p>
    </div>
  )
}
