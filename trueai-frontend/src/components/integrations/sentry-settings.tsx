'use client'

import { useState } from 'react'

import { clearSentrySecret, saveSentrySettings } from '@/app/actions/integrations'
import { Button } from '@/components/ui/button'
import { describedBy, Field, Input } from '@/components/ui/field'
import { ToneMark } from '@/components/ui/status'
import type { SentrySettings } from '@/lib/api/types'

/** Signing secret: verifies that webhook deliveries really come from your Sentry integration. */
export function SigningSecretForm({ settings }: { settings: SentrySettings }) {
  const [secret, setSecret] = useState('')
  const [state, setState] = useState<{ pending: boolean; error: string | null; saved: boolean }>({ pending: false, error: null, saved: false })

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setState({ pending: true, error: null, saved: false })
    const result = await saveSentrySettings({ webhook_secret: secret })
    setState({ pending: false, error: result.ok ? null : result.error, saved: result.ok })
    if (result.ok) setSecret('')
  }

  async function remove() {
    setState({ pending: true, error: null, saved: false })
    const result = await clearSentrySecret('webhook_secret')
    setState({ pending: false, error: result.ok ? null : result.error, saved: false })
  }

  return (
    <form onSubmit={save} className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[0.8125rem] font-medium text-ink">Signing secret</p>
        {settings.has_webhook_secret ? <ToneMark tone="fixed" label="Verifying deliveries" /> : <ToneMark tone="muted" label="Not set" />}
      </div>
      <Field
        id="webhook-secret"
        label={settings.has_webhook_secret ? 'Replace secret' : 'Client Secret from your Sentry integration'}
        error={state.error}
        hint="Stored encrypted. Once set, deliveries without a valid signature are rejected."
      >
        <Input
          id="webhook-secret"
          type="password"
          autoComplete="off"
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          aria-describedby={describedBy('webhook-secret', state.error)}
          aria-invalid={Boolean(state.error) || undefined}
        />
      </Field>
      <div className="flex items-center gap-3">
        <Button type="submit" size="sm" loading={state.pending} disabled={!secret.trim()}>
          Save secret
        </Button>
        {settings.has_webhook_secret && (
          <Button type="button" size="sm" variant="ghost" onClick={remove} disabled={state.pending}>
            Remove
          </Button>
        )}
        {state.saved && <span role="status" className="text-[0.8125rem] text-fixed">Saved.</span>}
      </div>
    </form>
  )
}

/** Optional Sentry API access, used to fetch the full event when a webhook has no stack trace. */
export function SentryApiForm({ settings }: { settings: SentrySettings }) {
  const [org, setOrg] = useState(settings.org_slug ?? '')
  const [token, setToken] = useState('')
  const [state, setState] = useState<{ pending: boolean; error: string | null; saved: boolean }>({ pending: false, error: null, saved: false })

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setState({ pending: true, error: null, saved: false })
    const result = await saveSentrySettings({ org_slug: org, auth_token: token || undefined })
    setState({ pending: false, error: result.ok ? null : result.error, saved: result.ok })
    if (result.ok) setToken('')
  }

  return (
    <form onSubmit={save} className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[0.8125rem] font-medium text-ink">API access</p>
        {settings.has_auth_token ? <ToneMark tone="fixed" label="Connected" /> : <ToneMark tone="muted" label="Not set" />}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="sentry-org" label="Organisation slug" hint="As in sentry.io/organizations/<slug>/">
          <Input id="sentry-org" value={org} onChange={(event) => setOrg(event.target.value)} spellCheck={false} className="font-mono" aria-describedby="sentry-org-hint" />
        </Field>
        <Field id="sentry-token" label={settings.has_auth_token ? 'Replace auth token' : 'Auth token'} error={state.error} hint="Needs event:read and org:read. Checked with Sentry before saving.">
          <Input
            id="sentry-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            aria-describedby={describedBy('sentry-token', state.error)}
            aria-invalid={Boolean(state.error) || undefined}
          />
        </Field>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" size="sm" loading={state.pending} disabled={!org.trim() || (!token.trim() && !settings.has_auth_token) || (org === (settings.org_slug ?? '') && !token)}>
          Save API access
        </Button>
        {state.saved && <span role="status" className="text-[0.8125rem] text-fixed">Saved and verified.</span>}
      </div>
    </form>
  )
}
